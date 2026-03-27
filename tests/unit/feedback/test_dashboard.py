import time

import pytest

from qtrader.feedback.dashboard import LiveGovernanceDashboard


@pytest.fixture
def dashboard() -> LiveGovernanceDashboard:
    """Initialize a LiveGovernanceDashboard for institutional operational certification."""
    return LiveGovernanceDashboard()


def test_dashboard_update_frequency_and_composition(dashboard: LiveGovernanceDashboard) -> None:
    """Verify that the dashboard accurately aggregates diverse system metric inputs."""
    perf = {"pnl": 100.0, "nav": 1100.0, "timestamp": time.time()}
    risk = {"drawdown": 0.02, "risk_score": 0.4}
    exec_data = {"fill_rate": 0.98, "slippage": 0.001}
    alloc = {"distribution_pct": {"Alpha1": 60.0, "Alpha2": 40.0}}

    report = dashboard.update_dashboard_state(perf, risk, exec_data, alloc)

    assert report["status"] == "DASHBOARD_SYNCHRONIZED"  # noqa: S101
    assert report["metrics"]["live_pnl"] == 100.0  # noqa: S101, PLR2004
    assert report["metrics"]["current_nav"] == 1100.0  # noqa: S101, PLR2004


def test_dashboard_stale_data_rejection(dashboard: LiveGovernanceDashboard) -> None:
    """Verify that the dashboard identifies and rejects stale metric artifacts (>1s)."""
    # 2 seconds old data.
    stale_ts = time.time() - 2.0
    perf = {"pnl": 100.0, "timestamp": stale_ts}

    report = dashboard.update_dashboard_state(perf, {}, {}, {})
    assert report["status"] == "STALE_DATA_ARTIFACT"  # noqa: S101


def test_dashboard_alert_trigger_logic(dashboard: LiveGovernanceDashboard) -> None:
    """Verify that the dashboard emits alerts on critical risk and execution breaches."""
    # Scenario: Risk Score 0.9 (CRITICAL) and Fill Rate 0.4 (FAILURE).
    perf = {"pnl": 0.0, "nav": 1000.0, "timestamp": time.time()}
    risk = {"drawdown": 0.15, "risk_score": 0.9}  # 2 Alerts
    exec_data = {"fill_rate": 0.4, "slippage": 0.01}  # 1 Alert

    report = dashboard.update_dashboard_state(perf, risk, exec_data, {})

    alerts = report["governance_status"]["active_alerts"]
    assert "RISK_CRITICAL: 0.90" in alerts  # noqa: S101
    assert "EXECUTION_FAILURE: 40.00%" in alerts  # noqa: S101
    assert "DRAWDOWN_BREACH: 15.00%" in alerts  # noqa: S101
    assert report["governance_status"]["operating_regime"] == "CRITICAL"  # noqa: S101


def test_dashboard_telemetry_tracking(dashboard: LiveGovernanceDashboard) -> None:
    """Verify situational awareness and forensic dashboard telemetry indexing."""
    perf = {"pnl": 0.0, "timestamp": time.time()}
    dashboard.update_dashboard_state(perf, {}, {}, {})
    dashboard.update_dashboard_state(perf, {}, {}, {})

    stats = dashboard.get_dashboard_telemetry()
    assert stats["total_refresh_cycles"] == 2  # noqa: S101, PLR2004
    assert stats["active_alert_count"] == 0  # noqa: S101
