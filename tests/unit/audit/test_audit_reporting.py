import pytest

from qtrader.audit.reporting_engine import ComplianceReportingEngine, ReportType


@pytest.fixture
def engine() -> ComplianceReportingEngine:
    """Initialize a ComplianceReportingEngine for institutional oversight."""
    return ComplianceReportingEngine(reporting_id="UNIT_TEST_AGGREGATOR")


def test_reporting_engine_daily_pnl_aggregation(engine: ComplianceReportingEngine) -> None:
    """Verify that daily trade entries aggregate correctly into Total PnL."""
    trades = [
        {"trade_id": "T1", "pnl": 500.0},
        {"trade_id": "T2", "pnl": -200.0},
        {"trade_id": "T3", "pnl": 150.0},
    ]

    report = engine.generate_report(ReportType.DAILY, trades, [], {"VaR": 0.02, "MaxDD": 0.01})

    # 500 - 200 + 150 = 450
    assert report["metrics"]["Platform_PnL"] == 450.0
    assert report["type"] == "DAILY"


def test_reporting_engine_incident_escalation(
    engine: ComplianceReportingEngine,
) -> None:
    """Verify that violation lists correctly escalate an INCIDENT report."""
    violations = [
        {"type": "WASH_TRADING", "id": "V1", "severity": "HIGH"},
        {"type": "SPOOFING", "id": "V2", "severity": "MEDIUM"},
    ]

    report = engine.generate_report(
        ReportType.INCIDENT, [], violations, {"VaR": 0.05, "MaxDD": 0.12}
    )

    assert report["metrics"]["Violation_Count"] == 2
    assert len(report["evidentiary_alerts"]) == 2
    assert report["type"] == "INCIDENT"


def test_reporting_engine_determinism_check(engine: ComplianceReportingEngine) -> None:
    """Verify that identical input produces identical structural metrics."""
    trades = [{"id": "T1", "pnl": 100.0}]
    violations = [{"id": "V1"}]
    risk = {"VaR": 0.02}

    report1 = engine.generate_report(ReportType.MONTHLY, trades, violations, risk)
    report2 = engine.generate_report(ReportType.MONTHLY, trades, violations, risk)

    # Structural values must be identical
    assert report1["metrics"] == report2["metrics"]
    assert report1["type"] == report2["type"]


def test_reporting_engine_empty_data_resilience(
    engine: ComplianceReportingEngine,
) -> None:
    """Verify that NULL and empty data are handled gracefully in aggregation."""
    # Empty lists
    report = engine.generate_report(ReportType.DAILY, [], [], {})

    assert report["metrics"]["Platform_PnL"] == 0.0
    assert report["metrics"]["Violation_Count"] == 0
    assert report["metrics"]["Terminal_VaR"] == 0.0


def test_reporting_engine_telemetry_reporting(
    engine: ComplianceReportingEngine,
) -> None:
    """Verify quaternary situational awareness for institutional aggregation cycles."""
    engine.generate_report(ReportType.DAILY, [], [], {})
    engine.generate_report(ReportType.DAILY, [], [], {})

    stats = engine.get_reporting_stats()
    assert stats["generation_count"] == 2
    assert stats["status"] == "AUDIT"
