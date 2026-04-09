import pytest
from qtrader.portfolio.risk_monitor import RealTimeRiskMonitor


@pytest.fixture
def monitor() -> RealTimeRiskMonitor:
    return RealTimeRiskMonitor(var_weight=0.3, dd_weight=0.5, exp_weight=0.2, risk_limit=1.0)


def test_monitor_risk_state_veracity(monitor: RealTimeRiskMonitor) -> None:
    live_data = {"var": 1.0, "drawdown": 1.0, "exposure": 1.0}
    report = monitor.evaluate_live_risk(live_data)
    assert report["result"] == "ALERT"
    assert report["level"] == "CRITICAL"
    assert report["metrics"]["risk_score_aggregated"] == 1.0


def test_monitor_weight_attribution(monitor: RealTimeRiskMonitor) -> None:
    live_data = {"var": 0.1, "drawdown": 2.0, "exposure": 0.1}
    report = monitor.evaluate_live_risk(live_data)
    assert report["metrics"]["risk_score_aggregated"] == 1.05
    assert report["metrics"]["cumulative_alert_count"] == 1


def test_monitor_normal_operation(monitor: RealTimeRiskMonitor) -> None:
    live_data = {"var": 0.1, "drawdown": 0.1, "exposure": 0.1}
    report = monitor.evaluate_live_risk(live_data)
    assert report["result"] == "PASS"
    assert report["level"] == "NORMAL"
    assert report["metrics"]["risk_score_aggregated"] == 0.1


def test_monitor_level_escalation_warnings(monitor: RealTimeRiskMonitor) -> None:
    report_elevated = monitor.evaluate_live_risk({"drawdown": 1.2})
    assert report_elevated["level"] == "ELEVATED"
    report_warning = monitor.evaluate_live_risk({"drawdown": 1.7})
    assert report_warning["level"] == "WARNING"


def test_monitor_telemetry_tracking(monitor: RealTimeRiskMonitor) -> None:
    monitor.evaluate_live_risk({"drawdown": 0.1})
    monitor.evaluate_live_risk({"drawdown": 2.0})
    stats = monitor.get_risk_telemetry()
    assert stats["total_alerts_lifecycle"] == 1
    assert stats["historical_peak_score"] == 1.0
    assert stats["status"] == "RISK_GOVERNANCE"
