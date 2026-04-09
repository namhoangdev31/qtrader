import pytest
from qtrader.compliance.risk_disclosure import RiskReportingEngine


@pytest.fixture
def engine() -> RiskReportingEngine:
    return RiskReportingEngine(reporting_id="UNIT_TEST_OVERSIGHT")


def test_risk_disclosure_var_calculation(engine: RiskReportingEngine) -> None:
    returns = [0.01] * 10
    equity = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    report = engine.generate_disclosure(equity, returns)
    assert report["metrics"]["VaR_99"] == 0.0
    assert report["metrics"]["Annualized_Vol"] == 0.0


def test_risk_disclosure_max_drawdown_logic(engine: RiskReportingEngine) -> None:
    equity = [100.0, 110.0, 100.0, 88.0, 95.0, 100.0]
    returns = [0.1, -0.09, -0.12, 0.07, 0.05]
    report = engine.generate_disclosure(equity, returns)
    assert report["metrics"]["Max_DD"] == 0.2


def test_risk_disclosure_data_fingerprint_reproducibility(engine: RiskReportingEngine) -> None:
    equity1 = [100.0, 110.0, 120.0]
    returns1 = [0.1, 0.09]
    report1 = engine.generate_disclosure(equity1, returns1)
    report2 = engine.generate_disclosure(equity1, returns1)
    assert report1["data_fingerprint"] == report2["data_fingerprint"]
    equity3 = [100.0, 105.0, 110.0]
    report3 = engine.generate_disclosure(equity3, returns1)
    assert report1["data_fingerprint"] != report3["data_fingerprint"]


def test_risk_disclosure_empty_data_resilience(engine: RiskReportingEngine) -> None:
    report = engine.generate_disclosure([], [])
    assert report["metrics"]["Sample_Size"] == 0
    assert report["metrics"]["VaR_99"] == 0.0
    assert report["metrics"]["Max_DD"] == 0.0


def test_risk_disclosure_telemetry_reporting(engine: RiskReportingEngine) -> None:
    engine.generate_disclosure([100, 101], [0.01])
    engine.generate_disclosure([101, 102], [0.009])
    report = engine.get_audit_stats()
    assert report["generation_count"] == 2
    assert report["status"] == "AUDIT"
