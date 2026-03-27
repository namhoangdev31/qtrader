import pytest

from qtrader.security.network_isolation import NetworkIsolationEnforcer, NetworkZone


@pytest.fixture
def enforcer() -> NetworkIsolationEnforcer:
    """Initialize a NetworkIsolationEnforcer with industrial defaults."""
    return NetworkIsolationEnforcer()


def test_authorized_network_paths(enforcer: NetworkIsolationEnforcer) -> None:
    """Verify that whitelisted cross-zone paths are ALLOWED."""
    # 1. TRADING -> RISK (Mandatory for order validation)
    assert enforcer.check_access(NetworkZone.TRADING, NetworkZone.RISK) is True  # noqa: S101

    # 2. TRADING -> COMPLIANCE (Audit logging)
    assert enforcer.check_access(NetworkZone.TRADING, NetworkZone.COMPLIANCE) is True  # noqa: S101

    # 3. RESEARCH -> COMPLIANCE (Alpha research audit)
    assert enforcer.check_access(NetworkZone.RESEARCH, NetworkZone.COMPLIANCE) is True  # noqa: S101


def test_forbidden_network_paths(enforcer: NetworkIsolationEnforcer) -> None:
    """Verify that critical forbidden paths (e.g., RESEARCH -> TRADING) are DENIED."""
    # 1. RESEARCH -> TRADING (Principal isolation gate)
    assert enforcer.check_access(NetworkZone.RESEARCH, NetworkZone.TRADING) is False  # noqa: S101

    # 2. PUBLIC -> TRADING (External ingress gate)
    assert enforcer.check_access(NetworkZone.PUBLIC, NetworkZone.TRADING) is False  # noqa: S101

    # 3. PUBLIC -> RISK (Risk firewall is protected)
    assert enforcer.check_access(NetworkZone.PUBLIC, NetworkZone.RISK) is False  # noqa: S101


def test_default_deny_logic(enforcer: NetworkIsolationEnforcer) -> None:
    """Verify that undefined paths (DEFAULT) are DENIED."""
    # 1. COMPLIANCE -> TRADING (Compliance is a sink only)
    assert enforcer.check_access(NetworkZone.COMPLIANCE, NetworkZone.TRADING) is False  # noqa: S101

    # 2. RISK -> PUBLIC (No direct external egress from risk firewall)
    assert enforcer.check_access(NetworkZone.RISK, NetworkZone.PUBLIC) is False  # noqa: S101

    # 3. TRADING -> RESEARCH (Execution results only via COMPLIANCE)
    assert enforcer.check_access(NetworkZone.TRADING, NetworkZone.RESEARCH) is False  # noqa: S101


def test_network_telemetry_reporting(enforcer: NetworkIsolationEnforcer) -> None:
    """Verify that network security telemetry correctly tracks denied connections."""
    # 1. ALLOW (TRADING -> RISK)
    enforcer.check_access(NetworkZone.TRADING, NetworkZone.RISK)
    # 2. DENY (PUBLIC -> TRADING)
    enforcer.check_access(NetworkZone.PUBLIC, NetworkZone.TRADING)

    report = enforcer.get_report()
    assert report["cross_zone_traffic"] == 2  # noqa: S101, PLR2004
    assert report["denied_connections"] == 1  # noqa: S101
    assert report["violation_rate"] == 0.5  # noqa: S101, PLR2004
