import pytest
from qtrader.analytics.accounting import FundAccountingEngine


@pytest.fixture
def engine() -> FundAccountingEngine:
    return FundAccountingEngine()


def test_accounting_mtm_pnl_accuracy(engine: FundAccountingEngine) -> None:
    pos = [{"symbol": "BTC/USD", "entry_price": 100.0, "quantity": 10.0}]
    market = {"BTC/USD": 105.0}
    report = engine.update_financial_state(pos, market)
    assert report["finances"]["unrealized_pnl"] == 50.0
    assert report["finances"]["net_asset_value"] == 1050.0


def test_accounting_nav_fidelity(engine: FundAccountingEngine) -> None:
    report = engine.update_financial_state([], {}, cash_balance=1000.0, liabilities=100.0)
    assert report["finances"]["net_asset_value"] == 900.0
    assert report["finances"]["liabilities_total"] == 100.0


def test_accounting_return_metrology(engine: FundAccountingEngine) -> None:
    pos = [{"symbol": "SOL/USD", "entry_price": 100.0, "quantity": 10.0}]
    market = {"SOL/USD": 105.0}
    report = engine.update_financial_state(pos, market, previous_nav=1000.0)
    assert report["performance"]["valuation_return"] == 0.05


def test_accounting_zero_capital_handling(engine: FundAccountingEngine) -> None:
    report = engine.update_financial_state([], {}, cash_balance=5000.0)
    assert report["finances"]["net_asset_value"] == 5000.0
    assert report["finances"]["unrealized_pnl"] == 0.0


def test_accounting_telemetry_tracking(engine: FundAccountingEngine) -> None:
    engine.update_financial_state([], {}, cash_balance=1000.0)
    engine.update_financial_state([], {}, cash_balance=1500.0)
    stats = engine.get_accounting_telemetry()
    assert stats["peak_nav_historical"] == 1500.0
    assert stats["total_valuation_cycles"] == 2
