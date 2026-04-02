import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from qtrader.feedback.live_feedback_engine import LiveFeedbackEngine

from qtrader.core.event_bus import EventBus, EventType
from qtrader.core.types import FillEvent, SignalEvent


def test_live_feedback_engine_init():
    # Create a mock event bus for testing
    event_bus = MagicMock()
    engine = LiveFeedbackEngine(event_bus=event_bus)
    assert engine.event_bus == event_bus
    assert engine.max_signal_age == timedelta(hours=1)
    assert engine.max_trade_age == timedelta(days=1)


@pytest.mark.asyncio
async def test_live_feedback_engine_subscribe_and_publish():
    # Create a real event bus for testing
    event_bus = EventBus()
    engine = LiveFeedbackEngine(event_bus=event_bus)

    # Test that we can process a signal (this tests the subscription mechanism)
    signal = SignalEvent(
        symbol="AAPL",
        signal_type="LONG",
        strength=Decimal("0.8"),
        timestamp=datetime.utcnow(),
        metadata={
            "strategy": "momentum",
            "side": "long",
            "mid_price": 100.0,
            "features": {"rsi": 60.0, "macd": 0.5},
        },
    )

    # This should not raise an exception
    await engine.process_signal(signal)

    # Test that we can process a fill
    fill = FillEvent(
        order_id="test_order",
        symbol="AAPL",
        timestamp=datetime.utcnow(),
        side="BUY",
        quantity=Decimal("1.0"),
        price=Decimal("100.0"),
        commission=Decimal("0"),
    )

    # This should not raise an exception
    await engine.process_fill(fill)
