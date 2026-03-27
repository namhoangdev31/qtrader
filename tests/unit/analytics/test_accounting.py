import pytest

from qtrader.analytics.accounting import FundAccountingEngine


@pytest.fixture
def engine() -> FundAccountingEngine:
    """Initialize a FundAccountingEngine for institutional financial certification."""
    return FundAccountingEngine()


def test_accounting_mtm_pnl_accuracy(engine: FundAccountingEngine) -> None:
    """Verify that unrealized PnL reflects the market price delta for long/short positions."""
    # Side: LONG (10). Entry 100. Market 105. PnL = 5 * 10 = 50.
    pos = [{"symbol": "BTC/USD", "entry_price": 100.0, "quantity": 10.0}]
    market = {"BTC/USD": 105.0}

    report = engine.update_financial_state(pos, market)
    assert report["finances"]["unrealized_pnl"] == 50.0  # noqa: S101, PLR2004
    assert report["finances"]["net_asset_value"] == 1050.0  # noqa: S101, PLR2004 (1000 + 50)


def test_accounting_nav_fidelity(engine: FundAccountingEngine) -> None:
    """Verify that liabilities are correctly subtracted from total assets."""
    # Cash 1000. Pos 0. Liabilities 100. NAV = 900.
    report = engine.update_financial_state([], {}, cash_balance=1000.0, liabilities=100.0)

    assert report["finances"]["net_asset_value"] == 900.0  # noqa: S101, PLR2004
    assert report["finances"]["liabilities_total"] == 100.0  # noqa: S101, PLR2004


def test_accounting_return_metrology(engine: FundAccountingEngine) -> None:
    """Verify return calculation accuracy ($D_{nav} / Nav_{lag}$)."""
    # Prev NAV 1000. New NAV 1050. Return = 0.05.
    pos = [{"symbol": "SOL/USD", "entry_price": 100.0, "quantity": 10.0}]
    market = {"SOL/USD": 105.0}  # Value 1050.

    report = engine.update_financial_state(pos, market, previous_nav=1000.0)
    assert report["performance"]["valuation_return"] == 0.05  # noqa: S101, PLR2004


def test_accounting_zero_capital_handling(engine: FundAccountingEngine) -> None:
    """Verify behavior when portfolio is liquid (only cash)."""
    # Cash 5000. No positions. No liabilities. NAV = 5000.
    report = engine.update_financial_state([], {}, cash_balance=5000.0)

    assert report["finances"]["net_asset_value"] == 5000.0  # noqa: S101, PLR2004
    assert report["finances"]["unrealized_pnl"] == 0.0  # noqa: S101


def test_accounting_telemetry_tracking(engine: FundAccountingEngine) -> None:
    """Verify situational awareness and financial forensics telemetry indexing."""
    engine.update_financial_state([], {}, cash_balance=1000.0)  # V1: NAV 1000
    engine.update_financial_state([], {}, cash_balance=1500.0)  # V2: NAV 1500

    stats = engine.get_accounting_telemetry()
    assert stats["peak_nav_historical"] == 1500.0  # noqa: S101, PLR2004
    assert stats["total_valuation_cycles"] == 2  # noqa: S101, PLR2004
