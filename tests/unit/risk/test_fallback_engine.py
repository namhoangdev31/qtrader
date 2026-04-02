"""Tests for [FAILSAFE_SYSTEM]: failure triggers fallback."""
import asyncio

import pytest

from qtrader.core.event import ErrorEvent, EventType, RiskEvent
from qtrader.core.event_bus import EventBus
from qtrader.core.events import ErrorPayload, RiskPayload
from qtrader.risk.fallback_engine import FallbackEngine, FallbackMode


@pytest.mark.asyncio
async def test_fallback_escalation_on_errors():
    """Consecutive errors escalate from NORMAL → REDUCED → HOLD → EMERGENCY."""
    bus = EventBus()
    await bus.start()
    engine = FallbackEngine(bus)
    await engine.start()

    assert engine.state.mode == FallbackMode.NORMAL
    assert engine.get_exposure_multiplier() == 1.0

    # Publish 2 errors → REDUCED
    for i in range(2):
        await bus.publish(ErrorEvent(
            source="test",
            payload=ErrorPayload(source="test", message=f"error_{i}", severity="HIGH")
        ))
    await asyncio.sleep(0.1)

    assert engine.state.mode == FallbackMode.REDUCED
    assert engine.get_exposure_multiplier() == 0.5

    # Publish 2 more → HOLD (total 4)
    for i in range(2):
        await bus.publish(ErrorEvent(
            source="test",
            payload=ErrorPayload(source="test", message=f"error_{i+2}", severity="HIGH")
        ))
    await asyncio.sleep(0.1)

    assert engine.state.mode == FallbackMode.HOLD
    assert engine.get_exposure_multiplier() == 0.0
    assert engine.is_trading_allowed() is False

    # 1 more → EMERGENCY (total 5)
    await bus.publish(ErrorEvent(
        source="test",
        payload=ErrorPayload(source="test", message="error_final", severity="HIGH")
    ))
    await asyncio.sleep(0.1)

    assert engine.state.mode == FallbackMode.EMERGENCY
    assert engine.get_exposure_multiplier() == 0.0


@pytest.mark.asyncio
async def test_critical_error_immediate_emergency():
    """A single CRITICAL error triggers immediate EMERGENCY."""
    bus = EventBus()
    await bus.start()
    engine = FallbackEngine(bus)
    await engine.start()

    await bus.publish(ErrorEvent(
        source="exchange",
        payload=ErrorPayload(source="exchange", message="Connection lost", severity="CRITICAL")
    ))
    await asyncio.sleep(0.1)

    assert engine.state.mode == FallbackMode.EMERGENCY
    assert engine.is_trading_allowed() is False


@pytest.mark.asyncio
async def test_risk_event_triggers_hold():
    """A non-fatal risk event transitions to HOLD."""
    bus = EventBus()
    await bus.start()
    engine = FallbackEngine(bus)
    await engine.start()

    await bus.publish(RiskEvent(
        source="test",
        payload=RiskPayload(
            symbol="BTC/USD",
            risk_type="DRAWDOWN",
            value=0.08,
            threshold=0.1,
            metrics={"drawdown": 0.08},
            metadata={"action": "REDUCE_EXPOSURE"}
        ),
    ))
    await asyncio.sleep(0.1)

    assert engine.state.mode == FallbackMode.HOLD


@pytest.mark.asyncio
async def test_trading_allowed_in_normal_and_reduced():
    """Trading is allowed in NORMAL and REDUCED modes."""
    bus = EventBus()
    engine = FallbackEngine(bus)

    engine.state.mode = FallbackMode.NORMAL
    assert engine.is_trading_allowed() is True

    engine.state.mode = FallbackMode.REDUCED
    assert engine.is_trading_allowed() is True

    engine.state.mode = FallbackMode.HOLD
    assert engine.is_trading_allowed() is False

    engine.state.mode = FallbackMode.EMERGENCY
    assert engine.is_trading_allowed() is False
