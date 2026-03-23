"""Simple test to verify LiveFeedbackEngine basic functionality."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from qtrader.feedback.live_feedback_engine import LiveFeedbackEngine
from qtrader.core.event_bus import EventBus


async def test_basic_functionality():
    """Test that the engine can be instantiated and processes events without error."""
    print("Testing LiveFeedbackEngine basic instantiation and event processing...")
    
    # Create event bus and feedback engine
    bus = EventBus()
    engine = LiveFeedbackEngine(
        event_bus=bus,
        max_signal_age=timedelta(minutes=5),
        max_trade_age=timedelta(minutes=10),
    )
    
    print("✓ LiveFeedbackEngine instantiated successfully")
    
    # Test that we can call the processing methods without error
    # (We won't check the metrics since matching is complex in this simple test)
    
    # Create a minimal signal
    signal = MagicMock()
    signal.symbol = "TEST"
    signal.timestamp = datetime.utcnow()
    signal.metadata = {
        "strategy": "test_strategy",
        "side": "long",
        "mid_price": 100.0,
        "features": {"test_feature": 1.0}
    }
    
    # Process signal - should not raise exception
    await engine.process_signal(signal)
    print("✓ Signal processed without error")
    
    # Create a minimal fill that should match the signal
    fill = MagicMock()
    fill.symbol = "TEST"
    fill.side = "buy"  # matches long signal
    fill.size = 1.0
    fill.price = 100.5  # slippage = +0.5
    fill.timestamp = datetime.utcnow() + timedelta(seconds=1)
    fill.metadata = {
        "strategy": "test_strategy"
    }
    
    # Process fill - should not raise exception
    await engine.process_fill(fill)
    print("✓ Fill processed without error")
    
    # Verify we can get metric DataFrames (they may be empty)
    feat_df = engine.get_feature_metrics()
    strat_df = engine.get_strategy_metrics()
    exec_df = engine.get_execution_metrics()
    
    print(f"✓ Feature metrics DataFrame retrieved: {feat_df.height} rows")
    print(f"✓ Strategy metrics DataFrame retrieved: {strat_df.height} rows")
    print(f"✓ Execution metrics DataFrame retrieved: {exec_df.height} rows")
    
    print("\n🎉 Basic functionality test passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    exit(0 if success else 1)