import time

from qtrader.portfolio.fee_tracker import FeeSnapshot, FeeTracker


def test_fee_tracker_initialization() -> None:
    """Test fee tracker initialization."""
    tracker = FeeTracker()

    assert tracker.maker_fees == 0.0
    assert tracker.taker_fees == 0.0
    assert tracker.funding_fees == 0.0
    assert tracker.withdrawal_fees == 0.0
    assert tracker.deposit_fees == 0.0
    assert tracker.total_fees == 0.0
    assert len(tracker.fee_history) == 0


def test_record_trade_fee_taker() -> None:
    """Test recording a taker fee."""
    tracker = FeeTracker()

    # Record a taker fee: price=100, qty=0.5, rate=0.001 (0.1%)
    fee = tracker.record_trade_fee(
        price=100.0,
        quantity=0.5,
        fee_rate=0.001,
        fee_type="taker",
        symbol="BTC-USDT",
        exchange="binance",
    )

    # Expected fee: 100 * 0.5 * 0.001 = 0.05
    assert fee == 0.05
    assert tracker.taker_fees == 0.05
    assert tracker.total_fees == 0.05
    assert tracker.symbol_fees["BTC-USDT"] == 0.05
    assert tracker.exchange_fees["binance"] == 0.05
    assert len(tracker.fee_history) == 1


def test_record_trade_fee_maker() -> None:
    """Test recording a maker fee."""
    tracker = FeeTracker()

    # Record a maker fee: price=50, qty=2.0, rate=0.0005 (0.05%)
    fee = tracker.record_trade_fee(
        price=50.0,
        quantity=2.0,
        fee_rate=0.0005,
        fee_type="maker",
        symbol="ETH-USDT",
        exchange="coinbase",
    )

    # Expected fee: 50 * 2.0 * 0.0005 = 0.05
    assert fee == 0.05
    assert tracker.maker_fees == 0.05
    assert tracker.total_fees == 0.05
    assert tracker.symbol_fees["ETH-USDT"] == 0.05
    assert tracker.exchange_fees["coinbase"] == 0.05


def test_record_trade_fee_withdrawal_deposit() -> None:
    """Test recording withdrawal and deposit fees."""
    tracker = FeeTracker()

    # Record withdrawal fee
    withdrawal_fee = tracker.record_trade_fee(
        price=1.0,  # Not used for withdrawal/deposit
        quantity=100.0,  # Amount
        fee_rate=0.01,  # 1% fee
        fee_type="withdrawal",
        symbol="USDT",
        exchange="kraken",
    )

    # Expected fee: 100 * 0.01 = 1.0
    assert withdrawal_fee == 1.0
    assert tracker.withdrawal_fees == 1.0

    # Record deposit fee
    deposit_fee = tracker.record_trade_fee(
        price=1.0,
        quantity=50.0,
        fee_rate=0.005,  # 0.5% fee
        fee_type="deposit",
        symbol="USDT",
        exchange="kraken",
    )

    # Expected fee: 50 * 0.005 = 0.25
    assert deposit_fee == 0.25
    assert tracker.deposit_fees == 0.25
    assert tracker.total_fees == 1.25  # 1.0 + 0.25


def test_record_funding_fee_long() -> None:
    """Test recording funding fee for long position."""
    tracker = FeeTracker()

    # Long position: we pay funding if rate > 0
    funding = tracker.record_funding_fee(
        position_size=1.5,  # 1.5 BTC long
        funding_rate=0.0001,  # 0.01%
        mark_price=30000.0,  # $30,000/BTC
        symbol="BTC-USDT",
        exchange="binance",
    )

    # Expected funding: 1.5 * 30000 * 0.0001 = 4.5 (we pay)
    assert funding == 4.5
    assert tracker.funding_fees == 4.5
    assert tracker.total_fees == 4.5
    assert tracker.symbol_fees["BTC-USDT"] == 4.5
    assert tracker.exchange_fees["binance"] == 4.5


def test_record_funding_fee_short() -> None:
    """Test recording funding fee for short position."""
    tracker = FeeTracker()

    # Short position: we receive funding if rate > 0 (negative cost)
    funding = tracker.record_funding_fee(
        position_size=-0.8,  # 0.8 BTC short
        funding_rate=0.0002,  # 0.02%
        mark_price=25000.0,  # $25,000/BTC
        symbol="BTC-USDT",
        exchange="bybit",
    )

    # Expected funding: -0.8 * 25000 * 0.0002 = -4.0 (we receive)
    assert funding == -4.0
    assert tracker.funding_fees == -4.0
    assert tracker.total_fees == -4.0
    assert tracker.symbol_fees["BTC-USDT"] == -4.0
    assert tracker.exchange_fees["bybit"] == -4.0


def test_fee_summary() -> None:
    """Test getting fee summary."""
    tracker = FeeTracker()

    # Add various fees
    tracker.record_trade_fee(100.0, 0.5, 0.001, "taker", "BTC", "binance")  # 0.05
    tracker.record_trade_fee(50.0, 2.0, 0.0005, "maker", "ETH", "coinbase")  # 0.05
    tracker.record_funding_fee(1.0, 0.0001, 30000.0, "BTC", "binance")  # 3.0
    tracker.record_trade_fee(1.0, 100.0, 0.01, "withdrawal", "USDT", "kraken")  # 1.0

    summary = tracker.get_fee_summary()

    assert summary["taker_fees"] == 0.05
    assert summary["maker_fees"] == 0.05
    assert summary["funding_fees"] == 3.0
    assert summary["withdrawal_fees"] == 1.0
    assert summary["deposit_fees"] == 0.0
    assert summary["total_fees"] == 4.1  # 0.05 + 0.05 + 3.0 + 1.0


def test_symbol_and_exchange_fees() -> None:
    """Test getting fees by symbol and exchange."""
    tracker = FeeTracker()

    # Add fees for different symbols and exchanges
    tracker.record_trade_fee(100.0, 0.5, 0.001, "taker", "BTC-USDT", "binance")  # 0.05
    tracker.record_trade_fee(100.0, 0.3, 0.001, "taker", "BTC-USDT", "coinbase")  # 0.03
    tracker.record_trade_fee(50.0, 2.0, 0.0005, "maker", "ETH-USDT", "binance")  # 0.05

    # Check symbol fees
    btc_fees = tracker.get_symbol_fees("BTC-USDT")
    assert btc_fees["BTC-USDT"] == 0.08  # 0.05 + 0.03

    eth_fees = tracker.get_symbol_fees("ETH-USDT")
    assert eth_fees["ETH-USDT"] == 0.05

    unknown_fees = tracker.get_symbol_fees("UNKNOWN")
    assert unknown_fees["UNKNOWN"] == 0.0

    all_symbols = tracker.get_symbol_fees()
    assert all_symbols["BTC-USDT"] == 0.08
    assert all_symbols["ETH-USDT"] == 0.05
    assert len(all_symbols) == 2

    # Check exchange fees
    binance_fees = tracker.get_exchange_fees("binance")
    assert binance_fees["binance"] == 0.10  # 0.05 + 0.05

    coinbase_fees = tracker.get_exchange_fees("coinbase")
    assert coinbase_fees["coinbase"] == 0.03

    unknown_exchange = tracker.get_exchange_fees("unknown")
    assert unknown_exchange["unknown"] == 0.0

    all_exchanges = tracker.get_exchange_fees()
    assert all_exchanges["binance"] == 0.10
    assert all_exchanges["coinbase"] == 0.03
    assert len(all_exchanges) == 2


def test_fee_history_tracking() -> None:
    """Test fee history snapshots."""
    tracker = FeeTracker()

    initial_time = time.time()
    time.sleep(0.01)  # Small delay to ensure different timestamps

    # Record first fee
    tracker.record_trade_fee(100.0, 0.5, 0.001, "taker", "BTC", "binance")
    first_snapshot = tracker.fee_history[-1]

    time.sleep(0.01)

    # Record second fee
    tracker.record_trade_fee(50.0, 2.0, 0.0005, "maker", "ETH", "coinbase")
    second_snapshot = tracker.fee_history[-1]

    # Check snapshots
    assert len(tracker.fee_history) == 2
    assert first_snapshot.taker_fees == 0.05
    assert first_snapshot.maker_fees == 0.0
    assert first_snapshot.total_fees == 0.05

    assert second_snapshot.taker_fees == 0.05
    assert second_snapshot.maker_fees == 0.05
    assert second_snapshot.total_fees == 0.10

    # Check timestamps are increasing
    assert second_snapshot.timestamp > first_snapshot.timestamp
    assert first_snapshot.timestamp >= initial_time


def test_get_recent_fees() -> None:
    """Test getting recent fee snapshots."""
    tracker = FeeTracker()

    # Record fees at different times
    time.time()
    tracker.record_trade_fee(100.0, 0.5, 0.001, "taker", "BTC", "binance")

    time.sleep(0.01)
    time2 = time.time()
    tracker.record_trade_fee(50.0, 2.0, 0.0005, "maker", "ETH", "coinbase")

    time.sleep(0.01)
    time3 = time.time()
    tracker.record_trade_fee(200.0, 0.1, 0.001, "taker", "BTC", "kraken")  # 0.02

    # Get fees since time2
    recent_fees = tracker.get_recent_fees(time2)
    assert len(recent_fees) == 2  # Should include time2 and time3 snapshots

    # Check that we got the right snapshots
    assert recent_fees[0].timestamp >= time2
    assert recent_fees[1].timestamp >= time2

    # Get fees since time3 (should only get the last one)
    very_recent = tracker.get_recent_fees(time3)
    assert len(very_recent) == 1
    assert very_recent[0].timestamp >= time3


def test_reset() -> None:
    """Test resetting the fee tracker."""
    tracker = FeeTracker()

    # Add some fees
    tracker.record_trade_fee(100.0, 0.5, 0.001, "taker", "BTC", "binance")
    tracker.record_funding_fee(1.0, 0.0001, 30000.0, "BTC", "binance")

    assert tracker.total_fees > 0
    assert len(tracker.fee_history) > 0
    assert len(tracker.symbol_fees) > 0
    assert len(tracker.exchange_fees) > 0

    # Reset
    tracker.reset()

    # Everything should be zero/empty
    assert tracker.maker_fees == 0.0
    assert tracker.taker_fees == 0.0
    assert tracker.funding_fees == 0.0
    assert tracker.withdrawal_fees == 0.0
    assert tracker.deposit_fees == 0.0
    assert tracker.total_fees == 0.0
    assert len(tracker.fee_history) == 0
    assert len(tracker.symbol_fees) == 0
    assert len(tracker.exchange_fees) == 0


def test_edge_cases() -> None:
    """Test edge cases."""
    tracker = FeeTracker()

    # Zero quantity or price should result in zero fee
    fee_zero_qty = tracker.record_trade_fee(100.0, 0.0, 0.001, "taker")
    assert fee_zero_qty == 0.0

    fee_zero_price = tracker.record_trade_fee(0.0, 0.5, 0.001, "taker")
    assert fee_zero_price == 0.0

    fee_zero_rate = tracker.record_trade_fee(100.0, 0.5, 0.0, "taker")
    assert fee_zero_rate == 0.0

    # Negative quantities should be handled via abs()
    fee_negative_qty = tracker.record_trade_fee(100.0, -0.5, 0.001, "taker")
    assert fee_negative_qty == 0.05  # abs(-0.5) = 0.5

    # Unknown fee type should default to taker
    fee_unknown_type = tracker.record_trade_fee(100.0, 0.5, 0.001, "unknown")
    assert tracker.taker_fees == 0.10  # 0.05 + 0.05
    assert fee_unknown_type == 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
