import pytest

from qtrader.analytics.reporting import InvestorReportingEngine


@pytest.fixture
def engine() -> InvestorReportingEngine:
    """Initialize an InvestorReportingEngine for institutional performance certification."""
    return InvestorReportingEngine()


def test_reporting_sharpe_accuracy(engine: InvestorReportingEngine) -> None:
    """Verify that the Sharpe ratio reflects the risk-adjusted excess return."""
    # NAV History: 1000 -> 1010 -> 1020 ... Linear growth.
    nav = [1000.0, 1010.0, 1020.0, 1030.0, 1040.0]
    # Return ~ 1% daily. Vol ~ 0.
    # Risk free 0.
    report = engine.generate_investor_analytics(nav, annual_risk_free_rate=0.0)

    assert report["risk_metrics"]["sharpe_ratio_basis"] > 10.0
    assert report["performance"]["total_cumulative_return_pct"] == 4.0


def test_reporting_max_drawdown_precision(engine: InvestorReportingEngine) -> None:
    """Verify that the drawdown forensics identifies the peak-to-trough valley."""
    # NAV History: Peak 1000 -> Valley 800 -> Recovery 900.
    # Max DD = (1000 - 800) / 1000 = 20%.
    nav = [1000.0, 900.0, 800.0, 900.0]
    report = engine.generate_investor_analytics(nav)

    assert report["risk_metrics"]["max_drawdown_captured_pct"] == 20.0


def test_reporting_annualized_volatility(engine: InvestorReportingEngine) -> None:
    """Verify that daily volatility is correctly annualized (sqrt(252))."""
    # Constant 1% returns. Vol = 0.
    nav = [100.0, 101.0, 102.01, 103.0301]
    report = engine.generate_investor_analytics(nav)

    # Vol should be effectively zero for geometric step.
    assert report["risk_metrics"]["annualized_volatility_pct"] < 1.0


def test_reporting_insufficient_data_resilience(engine: InvestorReportingEngine) -> None:
    """Verify behavior when reporting period dataset is minimal."""
    # Only 1 point. Minimum 2 required.
    report = engine.generate_investor_analytics([1000.0])
    assert report["status"] == "INSUFFICIENT_DATA"


def test_reporting_telemetry_tracking(engine: InvestorReportingEngine) -> None:
    """Verify situational awareness and forensic metric telemetry indexing."""
    engine.generate_investor_analytics([1000.0, 1100.0])
    engine.generate_investor_analytics([1100.0, 1200.0])

    stats = engine.get_reporting_telemetry()
    assert stats["total_reports_to_date"] == 2
    assert stats["peak_equity_historical"] == 1200.0
