"""Unit tests for capital accounting system."""

from __future__ import annotations

import pytest

from qtrader.portfolio.accounting import CapitalLedger, FeeEvent
from qtrader.oms.order_management_system import Position


def test_capital_ledger_initialization() -> None:
    """Test capital ledger initialization."""
    ledger = CapitalLedger()

    assert ledger.total_cash_usd == 0.0
    assert ledger.total_fees_paid == 0.0
    assert ledger.total_funding_paid == 0.0
    assert ledger.current_nav == 0.0
    assert ledger.previous_nav == 0.0
    assert ledger.exchange_rates["USD"] == 1.0


def test_exchange_rate_setting() -> None:
    """Test setting exchange rates."""
    ledger = CapitalLedger()

    ledger.set_exchange_rate("EUR", 1.1)
    assert ledger.exchange_rates["EUR"] == 1.1

    ledger.set_exchange_rate("BTC", 50000.0)
    assert ledger.exchange_rates["BTC"] == 50000.0


def test_cash_deposit_and_withdrawal() -> None:
    """Test cash deposit and withdrawal."""
    ledger = CapitalLedger()

    # Deposit 1000 USD
    ledger.record_cash_deposit(1000.0, "USD")
    assert ledger.total_cash_usd == 1000.0
    assert ledger.cash_balances["USD"] == 1000.0

    # Deposit 500 EUR (at 1.1 rate = 550 USD)
    ledger.set_exchange_rate("EUR", 1.1)
    ledger.record_cash_deposit(500.0, "EUR")
    assert ledger.total_cash_usd == 1550.0  # 1000 + 550
    assert ledger.cash_balances["EUR"] == 500.0

    # Withdraw 200 USD
    ledger.record_cash_withdrawal(200.0, "USD")
    assert ledger.total_cash_usd == 1350.0
    assert ledger.cash_balances["USD"] == 800.0


def test_insufficient_funds_withdrawal() -> None:
    """Test withdrawal with insufficient funds raises error."""
    ledger = CapitalLedger()
    ledger.record_cash_deposit(100.0, "USD")

    with pytest.raises(ValueError):
        ledger.record_cash_withdrawal(200.0, "USD")


def test_record_fee() -> None:
    """Test recording fees."""
    ledger = CapitalLedger()

    ledger.record_fee("binance", "BTC-USDT", 5.0, "2026-03-25T10:00:00Z", "taker")
    ledger.record_fee("binance", "ETH-USDT", 3.0, "2026-03-25T10:01:00Z", "maker")

    assert len(ledger.fees_paid) == 2
    assert ledger.total_fees_paid == 8.0

    # Check fee details
    assert ledger.fees_paid[0].exchange == "binance"
    assert ledger.fees_paid[0].symbol == "BTC-USDT"
    assert ledger.fees_paid[0].fee_type == "taker"
    assert ledger.fees_paid[0].amount == 5.0

    assert ledger.fees_paid[1].exchange == "binance"
    assert ledger.fees_paid[1].symbol == "ETH-USDT"
    assert ledger.fees_paid[1].fee_type == "maker"
    assert ledger.fees_paid[1].amount == 3.0


def test_record_funding_rate() -> None:
    """Test recording funding rates."""
    ledger = CapitalLedger()

    # Long position: we pay funding if rate > 0
    ledger.record_funding_rate("BTC-USDT", 0.0001, "2026-03-25T10:00:00Z", 1.0)  # 1 BTC long
    assert ledger.total_funding_paid == 0.0001  # We paid
    assert len(ledger.funding_payments) == 1

    # Short position: we receive funding if rate > 0
    ledger.record_funding_rate("BTC-USDT", 0.0001, "2026-03-25T10:05:00Z", -1.0)  # 1 BTC short
    assert ledger.total_funding_paid == 0.0  # 0.0001 + (-0.0001) = 0
    assert len(ledger.funding_payments) == 2


def test_nav_calculation() -> None:
    """Test NAV calculation."""
    ledger = CapitalLedger()

    # Start with some cash
    ledger.record_cash_deposit(10000.0, "USD")

    # Create positions
    positions = {
        "BTC-USDT": Position(symbol="BTC-USDT", qty=0.1, avg_cost=30000.0),
        "ETH-USDT": Position(symbol="ETH-USDT", qty=2.0, avg_cost=2000.0),
    }

    # Current prices
    prices = {"BTC-USDT": 32000.0, "ETH-USDT": 2100.0}

    # Calculate NAV
    nav = ledger.calculate_nav(positions, prices)

    # Cash: 10000.0
    # BTC position: 0.1 * 32000 = 3200.0
    # ETH position: 2.0 * 2100 = 4200.0
    # Total NAV: 10000 + 3200 + 4200 = 17400.0
    assert nav == 17400.0
    assert ledger.current_nav == 17400.0
    assert ledger.previous_nav == 0.0  # Previous NAV was 0 before first calculation


def test_daily_pnl_calculation() -> None:
    """Test daily P&L calculation."""
    ledger = CapitalLedger()

    # Initial state: cash only
    ledger.record_cash_deposit(10000.0, "USD")
    positions = {}
    prices = {}
    nav1 = ledger.calculate_nav(positions, prices)  # Should be 10000.0

    # Add positions
    positions = {
        "BTC-USDT": Position(symbol="BTC-USDT", qty=0.1, avg_cost=30000.0),
        "ETH-USDT": Position(symbol="ETH-USDT", qty=2.0, avg_cost=2000.0),
    }
    prices = {"BTC-USDT": 32000.0, "ETH-USDT": 2100.0}
    nav2 = ledger.calculate_nav(positions, prices)  # Should be 17400.0

    # Daily P&L should be nav2 - nav1 = 17400 - 10000 = 7400.0
    daily_pnl = ledger.calculate_daily_pnl()
    assert daily_pnl == 7400.0

    # Update prices and calculate again
    prices = {
        "BTC-USDT": 33000.0,  # BTC up 1000
        "ETH-USDT": 2200.0,  # ETH up 100
    }
    nav3 = ledger.calculate_nav(positions, prices)

    # New position value:
    # BTC: 0.1 * 33000 = 3300.0 (+100 from previous)
    # ETH: 2.0 * 2200 = 4400.0 (+200 from previous)
    # Cash: 10000.0 (unchanged)
    # Total: 10000 + 3300 + 4400 = 17700.0
    # Daily P&L should be 17700 - 17400 = 300.0
    daily_pnl = ledger.calculate_daily_pnl()
    assert daily_pnl == 300.0


def test_nav_components() -> None:
    """Test getting NAV components."""
    ledger = CapitalLedger()

    # Add some cash and fees
    ledger.record_cash_deposit(5000.0, "USD")
    ledger.record_fee("binance", "BTC-USDT", 10.0, "2026-03-25T10:00:00Z")

    positions = {"BTC-USDT": Position(symbol="BTC-USDT", qty=0.5, avg_cost=20000.0)}
    prices = {"BTC-USDT": 21000.0}

    components = ledger.get_nav_components(positions, prices)

    # Cash: 5000.0
    # Position: 0.5 * 21000 = 10500.0
    # NAV: 5000 + 10500 = 15500.0
    # Fees: 10.0

    assert abs(components["cash"] - 5000.0) < 0.01
    assert abs(components["position_value"] - 10500.0) < 0.01
    assert abs(components["nav"] - 15500.0) < 0.01
    assert abs(components["fees_paid"] - 10.0) < 0.01


def test_get_total_fees() -> None:
    """Test getting total fees in time period."""
    ledger = CapitalLedger()

    # Record fees at different times
    ledger.record_fee("binance", "BTC-USDT", 5.0, "2026-03-25T10:00:00Z")
    ledger.record_fee("binance", "ETH-USDT", 3.0, "2026-03-25T11:00:00Z")
    ledger.record_fee("kraken", "BTC-USDT", 2.0, "2026-03-25T12:00:00Z")

    # Get all fees
    total_all = ledger.get_total_fees()
    assert total_all == 10.0

    # Get fees from morning only
    total_morning = ledger.get_total_fees(
        start_timestamp="2026-03-25T10:00:00Z", end_timestamp="2026-03-25T11:30:00Z"
    )
    assert total_morning == 8.0  # 5.0 + 3.0

    # Get fees from afternoon only
    total_afternoon = ledger.get_total_fees(start_timestamp="2026-03-25T11:30:00Z")
    assert total_afternoon == 2.0  # Only the kraken fee


def test_fee_event_dataclass() -> None:
    """Test FeeEvent dataclass."""
    fee = FeeEvent(
        timestamp="2026-03-25T10:00:00Z",
        exchange="coinbase",
        symbol="BTC-USD",
        fee_type="taker",
        amount=15.5,
        metadata={"trade_id": "12345"},
    )

    assert fee.timestamp == "2026-03-25T10:00:00Z"
    assert fee.exchange == "coinbase"
    assert fee.symbol == "BTC-USD"
    assert fee.fee_type == "taker"
    assert fee.amount == 15.5
    assert fee.metadata == {"trade_id": "12345"}


def test_multi_currency_conversion() -> None:
    """Test multi-currency handling."""
    ledger = CapitalLedger()

    # Deposit in different currencies
    ledger.record_cash_deposit(1000.0, "USD")
    ledger.set_exchange_rate("EUR", 1.2)  # 1 EUR = 1.2 USD
    ledger.record_cash_deposit(1000.0, "EUR")  # Should be 1200 USD

    ledger.set_exchange_rate("JPY", 0.007)  # 1 JPY = 0.007 USD
    ledger.record_cash_deposit(100000.0, "JPY")  # Should be 700 USD

    # Total should be: 1000 + 1200 + 700 = 2900 USD
    assert ledger.total_cash_usd == 2900.0
    assert ledger.cash_balances["USD"] == 1000.0
    assert ledger.cash_balances["EUR"] == 1000.0
    assert ledger.cash_balances["JPY"] == 100000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
