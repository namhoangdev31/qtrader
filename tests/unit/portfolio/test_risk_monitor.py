import pytest

from qtrader.portfolio.risk_monitor import RealTimeRiskMonitor


@pytest.fixture
def monitor() -> RealTimeRiskMonitor:
    """Initialize a RealTimeRiskMonitor for institutional risk certification."""
    return RealTimeRiskMonitor(var_weight=0.3, dd_weight=0.5, exp_weight=0.2, risk_limit=1.0)


def test_monitor_risk_state_veracity(monitor: RealTimeRiskMonitor) -> None:
    """Verify that a high score correctly triggers the ALERT state and CRITICAL level."""
    # Weights: 0.3, 0.5, 0.2. Limit 1.0.
    # Metrics: VaR 1.0, DD 1.0, Exp 1.0. Score = 0.3*1 + 0.5*1 + 0.2*1 = 1.0.
    live_data = {"var": 1.0, "drawdown": 1.0, "exposure": 1.0}

    report = monitor.evaluate_live_risk(live_data)

    assert report["result"] == "ALERT"  # noqa: S101
    assert report["level"] == "CRITICAL"  # noqa: S101
    assert report["metrics"]["risk_score_aggregated"] == 1.0  # noqa: S101


def test_monitor_weight_attribution(monitor: RealTimeRiskMonitor) -> None:
    """Verify that increasing the weights correctly impacts the aggregated score."""
    # S1: Normal weights. Score = 0.3*0.1 + 0.5*2.0 + 0.2*0.1 = 0.03 + 1.0 + 0.02 = 1.05.
    live_data = {"var": 0.1, "drawdown": 2.0, "exposure": 0.1}
    report = monitor.evaluate_live_risk(live_data)

    assert report["metrics"]["risk_score_aggregated"] == 1.05  # noqa: S101, PLR2004
    assert report["metrics"]["cumulative_alert_count"] == 1  # noqa: S101


def test_monitor_normal_operation(monitor: RealTimeRiskMonitor) -> None:
    """Verify that a low-score portfolio returns the NORMAL risk level."""
    live_data = {"var": 0.1, "drawdown": 0.1, "exposure": 0.1}

    report = monitor.evaluate_live_risk(live_data)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["level"] == "NORMAL"  # noqa: S101
    assert report["metrics"]["risk_score_aggregated"] == 0.1  # noqa: S101, PLR2004


def test_monitor_level_escalation_warnings(monitor: RealTimeRiskMonitor) -> None:
    """Verify that the monitor correctly escalates through risk tiers."""
    # Score 0.6 (ELEVATED)
    report_elevated = monitor.evaluate_live_risk({"drawdown": 1.2})  # 0.5*1.2 = 0.6
    assert report_elevated["level"] == "ELEVATED"  # noqa: S101

    # Score 0.85 (WARNING)
    report_warning = monitor.evaluate_live_risk({"drawdown": 1.7})  # 0.5*1.7 = 0.85
    assert report_warning["level"] == "WARNING"  # noqa: S101


def test_monitor_telemetry_tracking(monitor: RealTimeRiskMonitor) -> None:
    """Verify situational awareness and peak risk score telemetry indexing."""
    monitor.evaluate_live_risk({"drawdown": 0.1})
    monitor.evaluate_live_risk({"drawdown": 2.0})  # Alert

    stats = monitor.get_risk_telemetry()
    assert stats["total_alerts_lifecycle"] == 1  # noqa: S101
    assert stats["historical_peak_score"] == 1.0  # noqa: S101
    assert stats["status"] == "RISK_GOVERNANCE"  # noqa: S101
