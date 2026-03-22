"""Final verification test for the LiveFeedbackEngine."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from qtrader.feedback.live_feedback_engine import LiveFeedbackEngine
from qtrader.core.event_bus import EventBus


async def test_complete_workflow():
    """Test a complete workflow with signal, entry fill, and exit fill."""
    print("Testing complete feedback workflow...")
    
    # Setup
    bus = EventBus()
    engine = LiveFeedbackEngine(
        event_bus=bus,
        max_signal_age=timedelta(minutes=5),
        max_trade_age=timedelta(minutes=10),
        feature_window=100,
        strategy_window=100,
        execution_window=100,
    )

    # Create a signal with metadata
    signal_time = datetime.utcnow()
    signal = MagicMock()
    signal.symbol = "AAPL"
    signal.timestamp = signal_time
    signal.metadata = {
        "strategy": "momentum",
        "side": "long",
        "mid_price": 100.0,
        "features": {"rsi": 60.0, "macd": 0.5, "volume_ratio": 1.2}
    }

    # Process the signal
    await engine.process_signal(signal)
    print(f"Signal processed: signal buffer size = {len(engine._signal_buffer)}")

    # Create a matching entry fill (buy for long signal)
    entry_time = signal_time + timedelta(seconds=5)
    fill_entry = MagicMock()
    fill_entry.symbol = "AAPL"
    fill_entry.side = "buy"  # matches long signal
    fill_entry.size = 10.0
    fill_entry.price = 100.5  # slippage = +0.5
    fill_entry.timestamp = entry_time
    fill_entry.metadata = {"strategy": "momentum"}  # Entry fills should also have strategy

    # Process the entry fill
    await engine.process_fill(fill_entry)
    print(f"Entry fill processed: open trades = {len(engine._open_trades)}, signal buffer = {len(engine._signal_buffer)}")

    # Create an exit fill (sell for long position)
    exit_time = signal_time + timedelta(minutes=2)
    fill_exit = MagicMock()
    fill_exit.symbol = "AAPL"
    fill_exit.side = "sell"  # opposite of buy
    fill_exit.size = 10.0
    fill_exit.price = 102.0  # profit
    fill_exit.timestamp = exit_time
    fill_exit.metadata = {"strategy": "momentum"}

    # Process the exit fill
    await engine.process_fill(fill_exit)
    print(f"Exit fill processed: open trades = {len(engine._open_trades)}")

    # Verify metrics were generated
    feat_df = engine.get_feature_metrics()
    strat_df = engine.get_strategy_metrics()
    exec_df = engine.get_execution_metrics()
    
    print(f"Feature metrics rows: {feat_df.height}")
    print(f"Strategy metrics rows: {strat_df.height}")
    print(f"Execution metrics rows: {exec_df.height}")
    
    # Debug: show the actual data
    if feat_df.height > 0:
        print("Feature metrics:")
        print(feat_df)
    if strat_df.height > 0:
        print("Strategy metrics:")
        print(strat_df)
    if exec_df.height > 0:
        print("Execution metrics:")
        print(exec_df)
    
    # Check feature metrics
    assert feat_df.height == 3, f"Expected 3 feature metrics, got {feat_df.height}"
    assert set(feat_df["feature_name"].to_list()) == {"rsi", "macd", "volume_ratio"}
    
    # Check strategy metrics
    assert strat_df.height == 1, f"Expected 1 strategy metric, got {strat_df.height}"
    expected_pnl = (102.0 - 100.5) * 10.0  # 1.5 * 10 = 15.0
    actual_pnl = strat_df["pnl"].to_list()[0]
    assert abs(actual_pnl - expected_pnl) < 0.001, f"Expected PnL {expected_pnl}, got {actual_pnl}"
    
    # Check execution metrics
    assert exec_df.height == 1, f"Expected 1 execution metric, got {exec_df.height}"
    expected_slippage = 0.5  # entry price - mid price = 100.5 - 100.0
    actual_slippage = exec_df["entry_slippage"].to_list()[0]
    assert abs(actual_slippage - expected_slippage) < 0.001, f"Expected slippage {expected_slippage}, got {actual_slippage}"
    
    print("✓ All metrics correctly generated and validated")
    
    # Test persistence
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmpdir:
        feat_path = os.path.join(tmpdir, "features.parquet")
        strat_path = os.path.join(tmpdir, "strategy.parquet")
        exec_path = os.path.join(tmpdir, "execution.parquet")
        
        await engine.persist_metrics(feat_path, strat_path, exec_path)
        
        # Verify files were created
        assert os.path.exists(feat_path)
        assert os.path.exists(strat_path)
        assert os.path.exists(exec_path)
        print("✓ Metrics successfully persisted to Parquet files")
    
    print("\n🎉 Complete workflow test passed!")


async def test_no_match_scenario():
    """Test scenario where fills don't match any signals."""
    print("\nTesting no-match scenario...")
    
    bus = EventBus()
    engine = LiveFeedbackEngine(event_bus=bus)
    
    # Create a fill with no preceding signal
    fill = MagicMock()
    fill.symbol = "AAPL"
    fill.side = "buy"
    fill.size = 10.0
    fill.price = 100.0
    fill.timestamp = datetime.utcnow()
    fill.metadata = {"strategy": "momentum"}
    
    # Should not crash and should not generate metrics
    await engine.process_fill(fill)
    
    assert engine.get_feature_metrics().is_empty()
    assert engine.get_strategy_metrics().is_empty()
    assert engine.get_execution_metrics().is_empty()
    
    print("✓ No-match scenario handled correctly")


async def test_stale_cleanup():
    """Test that stale signals and trades are cleaned up."""
    print("\nTesting stale cleanup...")
    
    bus = EventBus()
    engine = LiveFeedbackEngine(
        event_bus=bus,
        max_signal_age=timedelta(seconds=1),
        max_trade_age=timedelta(seconds=2),
    )
    
    # Create an old signal
    old_time = datetime.utcnow() - timedelta(seconds=5)
    old_signal = MagicMock()
    old_signal.symbol = "AAPL"
    old_signal.timestamp = old_time
    old_signal.metadata = {
        "strategy": "test",
        "side": "long",
        "mid_price": 100.0,
        "features": {"rsi": 50.0}
    }
    
    await engine.process_signal(old_signal)
    print("✓ Old signal buffered")
    
    # Wait for it to become stale and add a new signal to trigger cleanup
    new_time = datetime.utcnow()
    new_signal = MagicMock()
    new_signal.symbol = "AAPL"
    new_signal.timestamp = new_time
    new_signal.metadata = {
        "strategy": "test",
        "side": "long",
        "mid_price": 101.0,
        "features": {"rsi": 51.0}
    }
    
    await engine.process_signal(new_signal)
    print("✓ New signal processed (should trigger cleanup of old signal)")
    
    # Create a fill that would match the old signal but not the new one
    # Timing: after old signal but before new signal in real time,
    # but since we're using simulated time, we'll use a time between them
    fill_time = old_time + timedelta(seconds=2)  # 2 seconds after old signal
    fill = MagicMock()
    fill.symbol = "AAPL"
    fill.side = "buy"
    fill.size = 1.0
    fill.price = 100.0
    fill.timestamp = fill_time
    fill.metadata = {"strategy": "test"}
    
    # Process the fill - should not match anything because old signal was cleaned
    # and new signal hasn't been processed yet in real-time simulation
    await engine.process_fill(fill)
    
    # Should not have generated any metrics since no match occurred
    assert engine.get_execution_metrics().is_empty()
    print("✓ Stale signals properly cleaned up")


async def main():
    """Run all verification tests."""
    print("Running LiveFeedbackEngine verification tests...\n")
    
    await test_complete_workflow()
    await test_no_match_scenario()
    await test_stale_cleanup()
    
    print("\n✅ All verification tests passed!")
    print("\nThe LiveFeedbackEngine is ready for integration into QTrader.")


if __name__ == "__main__":
    asyncio.run(main())