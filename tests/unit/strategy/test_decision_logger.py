import asyncio
import uuid
from typing import Any, Dict
import pytest
from qtrader.core.event_bus import EventBus
from qtrader.core.config_manager import ConfigManager
from qtrader.strategy.decision_logger import DecisionLogger
from qtrader.core.events import DecisionTraceEvent, DecisionErrorEvent, EventType


@pytest.mark.asyncio
async def test_decision_logging_trace_capture():
    """Verify that the full analytical context is captured for a strategy decision."""
    bus = EventBus()
    config = ConfigManager(bus)
    logger = DecisionLogger(bus, config)
    
    await bus.start()
    
    trace_id = uuid.uuid4()
    features = {"price_momentum": 0.025, "rsi_14": 65.0, "volume_delta": 1.2}
    
    # Log a positive trading intention
    success = await logger.log_decision(
        trace_id=trace_id,
        model_id="XGBoost_Crypto_v2",
        features=features,
        signal=0.88,
        decision="BUY"
    )
    
    assert success is True
    
    # Give a small slice for bus internal workers
    await asyncio.sleep(0.01)
    
    # Verify metrics
    metrics = bus.get_metrics()
    assert metrics["total_processed"] >= 1
    
    await bus.stop()


@pytest.mark.asyncio
async def test_decision_logger_trace_linkage():
    """Verify that the decision logger maintains consistent trace_id across emits."""
    bus = EventBus()
    config = ConfigManager(bus)
    logger = DecisionLogger(bus, config)
    await bus.start()
    
    trace_id = uuid.uuid4()
    
    # Capture the events published to the bus
    captured_events = []
    async def mock_handler(event):
        captured_events.append(event)
        
    bus.subscribe(EventType.DECISION_TRACE, mock_handler)
    
    await logger.log_decision(
        trace_id=trace_id,
        model_id="SimpleLinear",
        features={"f1": 1.0},
        signal=0.5,
        decision="HOLD"
    )
    
    await asyncio.sleep(0.05)
    
    assert len(captured_events) == 1
    assert captured_events[0].trace_id == trace_id
    assert captured_events[0].payload.model_id == "SimpleLinear"
    
    await bus.stop()


@pytest.mark.asyncio
async def test_decision_logger_missing_trace_id():
    """Verify that the logger rejects decisions without a valid trace_id."""
    bus = EventBus()
    config = ConfigManager(bus)
    logger = DecisionLogger(bus, config)
    
    # Passing None/empty for trace_id should trigger failure
    success = await logger.log_decision(
        trace_id=None,
        model_id="ErrorTest",
        features={},
        signal=0.0,
        decision="HOLD"
    )
    
    assert success is False
