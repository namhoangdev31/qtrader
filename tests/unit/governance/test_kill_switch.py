from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import EventType
from qtrader.governance.kill_switch import KillSwitch

# Test Constants
STRATEGY_ID = "BTC_MOMENTUM_v1"


@pytest.mark.asyncio
async def test_kill_switch_trigger_drawdown() -> None:
    """Verify emergency shutdown upon drawdown threshold breach."""
    bus = AsyncMock()
    fsm = AsyncMock()
    fsm.transition.return_value = True
    
    # 10% Max Drawdown
    ks = KillSwitch(bus, fsm, max_drawdown=0.10)
    metrics = {"drawdown": 0.15, "pnl_change": -100.0, "slippage": 0.01}
    
    event = await ks.evaluate_metrics(STRATEGY_ID, metrics)
    
    # Validation
    assert event is not None
    assert event.payload.reason == "MAX_DRAWDOWN_BREACHED"
    assert event.payload.metric == "drawdown"
    
    # Transition
    assert fsm.transition.called
    fsm.transition.assert_called_with(
        STRATEGY_ID, "KILLED", reason="KILL_SWITCH_TRIGGERED: MAX_DRAWDOWN_BREACHED"
    )
    
    # Event
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.STRATEGY_KILL


@pytest.mark.asyncio
async def test_kill_switch_trigger_pnl_crash() -> None:
    """Verify emergency shutdown upon catastrophic PnL crash."""
    bus = AsyncMock()
    fsm = AsyncMock()
    
    # -1,000 PnL Crash threshold
    ks = KillSwitch(bus, fsm, pnl_crash_threshold=-1000.0)
    metrics = {"drawdown": 0.02, "pnl_change": -1500.0, "slippage": 0.005}
    
    event = await ks.evaluate_metrics(STRATEGY_ID, metrics)
    
    assert event is not None
    assert event.payload.reason == "PNL_CRASH_DETECTED"


@pytest.mark.asyncio
async def test_kill_switch_trigger_slippage() -> None:
    """Verify emergency shutdown upon anomalous slippage detection."""
    bus = AsyncMock()
    fsm = AsyncMock()
    
    # 5% Slippage limit
    ks = KillSwitch(bus, fsm, slippage_limit=0.05)
    metrics = {"drawdown": 0.01, "pnl_change": 10.0, "slippage": 0.08}
    
    event = await ks.evaluate_metrics(STRATEGY_ID, metrics)
    
    assert event is not None
    assert event.payload.reason == "ANOMALOUS_SLIPPAGE_DETECTED"


@pytest.mark.asyncio
async def test_kill_switch_normal_operation() -> None:
    """Verify NO action is taken during healthy metrics playback."""
    bus = AsyncMock()
    fsm = AsyncMock()
    ks = KillSwitch(bus, fsm)
    
    metrics = {"drawdown": 0.02, "pnl_change": 10.0, "slippage": 0.001}
    event = await ks.evaluate_metrics(STRATEGY_ID, metrics)
    
    assert event is None
    assert not fsm.transition.called
    assert not bus.publish.called


@pytest.mark.asyncio
async def test_kill_switch_system_failure() -> None:
    """Verify industrial error handling during kill-switch-level exceptions."""
    bus = AsyncMock()
    fsm = AsyncMock()
    ks = KillSwitch(bus, fsm)
    
    # Faulty inputs causing exception
    event = await ks.evaluate_metrics(STRATEGY_ID, None) # type: ignore
    
    assert event is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.KILL_ERROR
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)
