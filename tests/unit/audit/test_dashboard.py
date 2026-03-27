import pytest

from qtrader.audit.dashboard import GovernanceDashboard, UserRole


@pytest.fixture
def dashboard() -> GovernanceDashboard:
    """Initialize a GovernanceDashboard for institutional oversight."""
    return GovernanceDashboard()


def test_dashboard_trader_role_redaction(dashboard: GovernanceDashboard) -> None:
    """Verify that sensitive violation fields are redacted for the TRADER role."""
    violations = [{"type": "WASH_TRADING", "id": "V1", "severity": "HIGH", "timestamp": 1e9}]

    # Render with TRADER role
    view = dashboard.render_view(
        UserRole.TRADER,
        {"pnl": 1000.0, "equity": 100000.0},
        {"VaR": 0.02, "MaxDD": 0.01},
        violations,
        "NORMAL",
    )

    # Check that ID and severity are redacted
    trader_alert = view["telemetry"]["alerts"][0]
    assert trader_alert["type"] == "WASH_TRADING"  # noqa: S101
    assert "id" not in trader_alert  # noqa: S101
    assert "severity" not in trader_alert  # noqa: S101


def test_dashboard_auditor_full_forensics(dashboard: GovernanceDashboard) -> None:
    """Verify that the AUDITOR role receives full forensic evidence chains."""
    violations = [{"type": "SPOOFING", "id": "V2", "severity": "MEDIUM", "timestamp": 1.1e9}]

    # Render with AUDITOR role
    view = dashboard.render_view(
        UserRole.AUDITOR,
        {"pnl": 1000.0, "equity": 100000.0},
        {"VaR": 0.02, "MaxDD": 0.01},
        violations,
        "NORMAL",
    )

    # Check for full data presence
    auditor_alert = view["telemetry"]["alerts"][0]
    assert auditor_alert["id"] == "V2"  # noqa: S101
    assert auditor_alert["severity"] == "MEDIUM"  # noqa: S101


def test_dashboard_access_logging_integrity(dashboard: GovernanceDashboard) -> None:
    """Verify that every dashboard refresh generates a forensic access log entry."""
    dashboard.render_view(UserRole.RISK_MANAGER, {}, {}, [], "HALTED")
    dashboard.render_view(UserRole.AUDITOR, {}, {}, [], "HALTED")

    stats = dashboard.get_visibility_telemetry()
    assert stats["access_count"] == 2  # noqa: S101, PLR2004
    assert stats["status"] == "VISIBILITY"  # noqa: S101


def test_dashboard_performance_sync_accuracy(dashboard: GovernanceDashboard) -> None:
    """Verify that the rendered view perfectly matches the platform performance state."""
    pnl = 450.5
    equity = 99550.0

    view = dashboard.render_view(UserRole.TRADER, {"pnl": pnl, "equity": equity}, {}, [], "NORMAL")

    assert view["telemetry"]["performance"]["Total_PnL"] == pnl  # noqa: S101
    assert view["telemetry"]["performance"]["Core_Equity"] == equity  # noqa: S101


def test_dashboard_latency_telemetry_check(dashboard: GovernanceDashboard) -> None:
    """Verify that refresh latency is tracked correctly for sub-second visibility monitoring."""
    view = dashboard.render_view(UserRole.TRADER, {}, {}, [], "NORMAL")
    assert view["refresh_latency_ms"] >= 0.0  # noqa: S101 (Float check)
    assert view["status"] == "DASHBOARD_LIVE"  # noqa: S101
