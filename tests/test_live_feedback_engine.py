"""Unit tests for the LiveFeedbackEngine."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import asyncio
import polars as pl

from qtrader.feedback.live_feedback_engine import LiveFeedbackEngine
from qtrader.core.event_bus import EventBus, EventType


def run_async(coro):
    """Helper to run an async function in a test."""
    return asyncio.run(coro)


def test_feedback_engine_basic() -> None:
    """Test basic functionality of the feedback engine."""
    async def _test():
        bus = EventBus()
        engine = LiveFeedbackEngine(
            event_bus=bus,
            max_signal_age=timedelta(minutes=5),
            max_trade_age=timedelta(minutes=10),
            feature_window=10,
            strategy_window=10,
            execution_window=10,
        )

        # Create a mock signal with proper metadata
        signal = MagicMock()
        signal.symbol = "AAPL"
        signal.timestamp = datetime.utcnow()
        signal.metadata = {
            "strategy": "momentum",
            "side": "long",
            "mid_price": 100.0,
            "features": {"rsi": 60.0, "macd": 0.5}
        }
        # Also set direct attributes for backward compatibility
        signal.strategy = "momentum"
        signal.side = "long"
        signal.mid_price = 100.0
        signal.features = {"rsi": 60.0, "macd": 0.5}

        # Process the signal
        await engine.process_signal(signal)

        # Create a matching fill (entry) with metadata
        fill_entry = MagicMock()
        fill_entry.symbol = "AAPL"
        fill_entry.side = "buy"
        fill_entry.size = 10.0
        fill_entry.price = 100.5  # slippage = +0.5
        fill_entry.timestamp = signal.timestamp + timedelta(seconds=10)
        fill_entry.metadata = {
            "strategy": "momentum"
        }

        # Process the entry fill
        await engine.process_fill(fill_entry)

        # Create an exit fill (opposite side) with metadata
        fill_exit = MagicMock()
        fill_exit.symbol = "AAPL"
        fill_exit.side = "sell"
        fill_exit.size = 10.0
        fill_exit.price = 102.0  # profit
        fill_exit.timestamp = signal.timestamp + timedelta(minutes=5)
        fill_exit.metadata = {
            "strategy": "momentum"
        }

        # Process the exit fill
        await engine.process_fill(fill_exit)

        # Check metrics
        feat_df = engine.get_feature_metrics()
        assert feat_df.height == 2  # two features
        assert set(feat_df["feature_name"].to_list()) == {"rsi", "macd"}
        # For a long trade: (102.0 - 100.5) / 100.5 = 0.0149 ~= 1.5% return
        expected_return = (102.0 - 100.5) / 100.5
        realized_returns = feat_df["realized_return"].to_list()
        assert len(realized_returns) == 2
        for r in realized_returns:
            assert abs(r - expected_return) < 0.001

        strat_df = engine.get_strategy_metrics()
        assert strat_df.height == 1
        expected_pnl = (102.0 - 100.5) * 10.0  # 1.5 * 10 = 15.0
        pnls = strat_df["pnl"].to_list()
        assert len(pnls) == 1
        assert abs(pnls[0] - expected_pnl) < 0.001

        exec_df = engine.get_execution_metrics()
        assert exec_df.height == 1
        slippages = exec_df["entry_slippage"].to_list()
        assert len(slippages) == 1
        assert abs(slippages[0] - 0.5) < 0.001

    run_async(_test())
    print("✓ Basic feedback engine test passed")


def test_feedback_engine_short() -> None:
    """Test feedback engine with a short trade."""
    async def _test():
        bus = EventBus()
        engine = LiveFeedbackEngine(
            event_bus=bus,
            max_signal_age=timedelta(minutes=5),
            max_trade_age=timedelta(minutes=10),
        )

        # Create a mock signal for short with proper metadata
        signal = MagicMock()
        signal.symbol = "AAPL"
        signal.timestamp = datetime.utcnow()
        signal.metadata = {
            "strategy": "mean_reversion",
            "side": "short",
            "mid_price": 100.0,
            "features": {"rsi": 40.0}
        }
        # Also set direct attributes for backward compatibility
        signal.strategy = "mean_reversion"
        signal.side = "short"
        signal.mid_price = 100.0
        signal.features = {"rsi": 40.0}

        # Process the signal
        await engine.process_signal(signal)

        # Create a matching fill (entry for short = sell)
        fill_entry = MagicMock()
        fill_entry.symbol = "AAPL"
        fill_entry.side = "sell"
        fill_entry.size = 5.0
        fill_entry.price = 100.5  # slippage = +0.5 (sold at higher than mid price)
        fill_entry.timestamp = signal.timestamp + timedelta(seconds=10)

        # Process the entry fill
        await engine.process_fill(fill_entry)

        # Create an exit fill (opposite side for short = buy)
        fill_exit = MagicMock()
        fill_exit.symbol = "AAPL"
        fill_exit.side = "buy"
        fill_exit.size = 5.0
        fill_exit.price = 98.0  # bought back lower -> profit
        fill_exit.timestamp = signal.timestamp + timedelta(minutes=5)

        # Process the exit fill
        await engine.process_fill(fill_exit)

        # Check metrics
        feat_df = engine.get_feature_metrics()
        assert feat_df.height == 1
        # For a short trade: (100.5 - 98.0) / 100.5 = 0.0249 ~= 2.5% return
        expected_return = (100.5 - 98.0) / 100.5
        realized_returns = feat_df["realized_return"].to_list()
        assert len(realized_returns) == 1
        assert abs(realized_returns[0] - expected_return) < 0.001

        strat_df = engine.get_strategy_metrics()
        assert strat_df.height == 1
        expected_pnl = (100.5 - 98.0) * 5.0  # 2.5 * 5 = 12.5
        pnls = strat_df["pnl"].to_list()
        assert len(pnls) == 1
        assert abs(pnls[0] - expected_pnl) < 0.001

        exec_df = engine.get_execution_metrics()
        assert exec_df.height == 1
        # For short: slippage = fill_price - mid_price = 100.5 - 100.0 = +0.5
        slippages = exec_df["entry_slippage"].to_list()
        assert len(slippages) == 1
        assert abs(slippages[0] - 0.5) < 0.001

    run_async(_test())
    print("✓ Short trade feedback engine test passed")


def test_feedback_engine_no_match() -> None:
    """Test that unmatched fills are handled gracefully."""
    async def _test():
        bus = EventBus()
        engine = LiveFeedbackEngine(event_bus=bus)

        # Create a fill with no matching signal
        fill = MagicMock()
        fill.symbol = "AAPL"
        fill.side = "buy"
        fill.size = 10.0
        fill.price = 100.0
        fill.timestamp = datetime.utcnow()

        # Should not raise an exception
        await engine.process_fill(fill)

        # Metrics should be empty
        assert engine.get_feature_metrics().is_empty()
        assert engine.get_strategy_metrics().is_empty()
        assert engine.get_execution_metrics().is_empty()

    run_async(_test())
    print("✓ No-match fill test passed")


def test_feedback_engine_stale_cleanup() -> None:
    """Test that stale signals and trades are cleaned up."""
    async def _test():
        bus = EventBus()
        engine = LiveFeedbackEngine(
            event_bus=bus,
            max_signal_age=timedelta(seconds=1),
            max_trade_age=timedelta(seconds=2),
        )

        # Create an old signal
        old_time = datetime.utcnow() - timedelta(seconds=5)
        signal = MagicMock()
        signal.symbol = "AAPL"
        signal.strategy = "test"
        signal.side = "long"
        signal.timestamp = old_time
        signal.mid_price = 100.0
        signal.features = {"rsi": 50.0}

        await engine.process_signal(signal)

        # Buffer should be cleaned up automatically on next signal processing
        # Create a new recent signal to trigger cleanup
        new_signal = MagicMock()
        new_signal.symbol = "AAPL"
        new_signal.strategy = "test"
        new_signal.side = "long"
        new_signal.timestamp = datetime.utcnow()
        new_signal.mid_price = 101.0
        new_signal.features = {"rsi": 51.0}

        await engine.process_signal(new_signal)

        # The old signal should have been removed
        # We can't directly access the buffer, but we can verify by trying to match
        # Create a fill that would match the old signal but not the new one
        fill = MagicMock()
        fill.symbol = "AAPL"
        fill.side = "buy"
        fill.size = 1.0
        fill.price = 100.0
        fill.timestamp = old_time + timedelta(seconds=1)  # After old signal, before new

        await engine.process_fill(fill)

        # Should not match because old signal was cleaned up
        assert engine.get_execution_metrics().is_empty()

    run_async(_test())
    print("✓ Stale cleanup test passed")


if __name__ == "__main__":
    test_feedback_engine_basic()
    test_feedback_engine_short()
    test_feedback_engine_no_match()
    test_feedback_engine_stale_cleanup()
    print("\n✅ All LiveFeedbackEngine unit tests passed!")