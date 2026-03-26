import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from qtrader.core.config_manager import ConfigManager
from qtrader.core.event_bus import EventBus
from qtrader.core.events import EventType
from qtrader.strategy.decision_logger import DecisionLogger

# Constants for testing to avoid magic number warnings
MODEL_ID = "XGBoost_Crypto_v2"
BUY_DECISION = "BUY"
HOLD_DECISION = "HOLD"
F1 = 0.025
F2 = 65.0
SIGNAL_BUY = 0.88
SIGNAL_HOLD = 0.5
VERSION_42 = 42


class MockConfigManager(ConfigManager):
    """Minimal mock that returns a deterministic version."""
    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)

    def get_current_version(self) -> int:
        return VERSION_42


@pytest.mark.asyncio
async def test_decision_logging_trace_capture() -> None:
    """Verify that the full analytical context is captured for a strategy decision."""
    bus = EventBus()
    config = MockConfigManager(bus)
    decision_logger = DecisionLogger(bus, config)
    
    await bus.start()
    
    trace_id = uuid.uuid4()
    features = {"price_momentum": F1, "rsi_14": F2}
    
    success = await decision_logger.log_decision(
        trace_id=trace_id,
        model_id=MODEL_ID,
        features=features,
        signal=SIGNAL_BUY,
        decision=BUY_DECISION
    )
    
    assert success is True # noqa: S101
    
    await asyncio.sleep(0.01)
    
    metrics = decision_logger.get_metrics()
    assert metrics["total_decisions"] == 1 # noqa: S101
    assert metrics["decision_logged_rate"] == 1.0 # noqa: S101
    assert metrics["coverage_100"] is True # noqa: S101
    
    await bus.stop()


@pytest.mark.asyncio
async def test_decision_logger_rejection_on_missing_features() -> None:
    """Verify that empty feature vector results in trade rejection and ErrorEvent."""
    bus = EventBus()
    config = MockConfigManager(bus)
    decision_logger = DecisionLogger(bus, config)
    await bus.start()
    
    trace_id = uuid.uuid4()
    captured_events = []
    
    async def capture_err_handler(event: Any) -> None:
        captured_events.append(event)
        
    bus.subscribe(EventType.DECISION_ERROR, capture_err_handler)
    
    # Passing empty features should trigger rejection
    result = await decision_logger.log_decision(
        trace_id=trace_id,
        model_id="BrokenModel",
        features={}, # Empty features
        signal=0.0,
        decision=HOLD_DECISION
    )
    
    assert result is False # noqa: S101
    
    await asyncio.sleep(0.05)
    
    assert len(captured_events) == 1 # noqa: S101
    assert captured_events[0].payload.error_type == "MISSING_FEATURES" # noqa: S101
    assert captured_events[0].trace_id == trace_id # noqa: S101
    
    await bus.stop()


@pytest.mark.asyncio
async def test_decision_logger_publish_failure() -> None:
    """Verify handling when event bus refuses to publish (e.g. backpressure)."""
    bus = EventBus()
    config = MockConfigManager(bus)
    decision_logger = DecisionLogger(bus, config)
    await bus.start()
    
    trace_id = uuid.uuid4()
    
    # Mock publish to return False (simulating backpressure drop)
    with patch.object(bus, "publish", new_callable=AsyncMock) as mock_publish:
        mock_publish.return_value = False
        
        result = await decision_logger.log_decision(
            trace_id=trace_id,
            model_id="FullBus",
            features={"f1": 1.0},
            signal=0.0,
            decision=HOLD_DECISION
        )
        
        assert result is False # noqa: S101
        metrics = decision_logger.get_metrics()
        assert metrics["decision_logged_rate"] == 0.0 # noqa: S101
    
    await bus.stop()


@pytest.mark.asyncio
async def test_decision_logger_critical_error_handling() -> None:
    """Verify that the system halts and notifies on internal logger exceptions."""
    bus = EventBus()
    config = MockConfigManager(bus)
    decision_logger = DecisionLogger(bus, config)
    await bus.start()
    
    trace_id = uuid.uuid4()
    captured_events = []
    
    async def capture_err_handler(event: Any) -> None:
        captured_events.append(event)
        
    bus.subscribe(EventType.DECISION_ERROR, capture_err_handler)
    
    with patch.object(config, "get_current_version", side_effect=ValueError("Test Exception")):
        result = await decision_logger.log_decision(
            trace_id=trace_id,
            model_id="CrashModel",
            features={"f1": 1.0},
            signal=0.0,
            decision=HOLD_DECISION
        )
        
        assert result is False # noqa: S101
        
        await asyncio.sleep(0.05)
        assert len(captured_events) == 1 # noqa: S101
        assert captured_events[0].payload.error_type == "SYSTEM_FAILURE" # noqa: S101
        assert "Test Exception" in captured_events[0].payload.details # noqa: S101
    
    await bus.stop()


@pytest.mark.asyncio
async def test_decision_logger_trace_linkage() -> None:
    """Verify that the decision logger maintains consistent trace_id across emits."""
    bus = EventBus()
    config = MockConfigManager(bus)
    decision_logger = DecisionLogger(bus, config)
    await bus.start()
    
    trace_id = uuid.uuid4()
    captured_events = []
    
    async def mock_handler(event: Any) -> None:
        captured_events.append(event)
        
    bus.subscribe(EventType.DECISION_TRACE, mock_handler)
    
    await decision_logger.log_decision(
        trace_id=trace_id,
        model_id="SimpleLinear",
        features={"f1": 1.0},
        signal=SIGNAL_HOLD,
        decision=HOLD_DECISION
    )
    
    await asyncio.sleep(0.05)
    
    assert len(captured_events) == 1 # noqa: S101
    assert captured_events[0].trace_id == trace_id # noqa: S101
    assert captured_events[0].payload.model_id == "SimpleLinear" # noqa: S101
    assert captured_events[0].payload.config_version == VERSION_42 # noqa: S101
    
    await bus.stop()
