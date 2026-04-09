import pytest
from qtrader.analytics.reporting import InvestorReportingEngine


@pytest.fixture
def engine() -> InvestorReportingEngine:
    return InvestorReportingEngine()


def test_reporting_sharpe_accuracy(engine: InvestorReportingEngine) -> None:
    nav = [1000.0, 1010.0, 1020.0, 1030.0, 1040.0]
    report = engine.generate_investor_analytics(nav, annual_risk_free_rate=0.0)
    assert report["risk_metrics"]["sharpe_ratio_basis"] > 10.0
    assert report["performance"]["total_cumulative_return_pct"] == 4.0


def test_reporting_max_drawdown_precision(engine: InvestorReportingEngine) -> None:
    nav = [1000.0, 900.0, 800.0, 900.0]
    report = engine.generate_investor_analytics(nav)
    assert report["risk_metrics"]["max_drawdown_captured_pct"] == 20.0


def test_reporting_annualized_volatility(engine: InvestorReportingEngine) -> None:
    nav = [100.0, 101.0, 102.01, 103.0301]
    report = engine.generate_investor_analytics(nav)
    assert report["risk_metrics"]["annualized_volatility_pct"] < 1.0


def test_reporting_insufficient_data_resilience(engine: InvestorReportingEngine) -> None:
    report = engine.generate_investor_analytics([1000.0])
    assert report["status"] == "INSUFFICIENT_DATA"


def test_reporting_telemetry_tracking(engine: InvestorReportingEngine) -> None:
    engine.generate_investor_analytics([1000.0, 1100.0])
    engine.generate_investor_analytics([1100.0, 1200.0])
    stats = engine.get_reporting_telemetry()
    assert stats["total_reports_to_date"] == 2
    assert stats["peak_equity_historical"] == 1200.0
