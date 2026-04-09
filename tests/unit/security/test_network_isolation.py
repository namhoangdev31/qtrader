import pytest
from qtrader.security.network_isolation import NetworkIsolationEnforcer, NetworkZone


@pytest.fixture
def enforcer() -> NetworkIsolationEnforcer:
    return NetworkIsolationEnforcer()


def test_authorized_network_paths(enforcer: NetworkIsolationEnforcer) -> None:
    assert enforcer.check_access(NetworkZone.TRADING, NetworkZone.RISK) is True
    assert enforcer.check_access(NetworkZone.TRADING, NetworkZone.COMPLIANCE) is True
    assert enforcer.check_access(NetworkZone.RESEARCH, NetworkZone.COMPLIANCE) is True


def test_forbidden_network_paths(enforcer: NetworkIsolationEnforcer) -> None:
    assert enforcer.check_access(NetworkZone.RESEARCH, NetworkZone.TRADING) is False
    assert enforcer.check_access(NetworkZone.PUBLIC, NetworkZone.TRADING) is False
    assert enforcer.check_access(NetworkZone.PUBLIC, NetworkZone.RISK) is False


def test_default_deny_logic(enforcer: NetworkIsolationEnforcer) -> None:
    assert enforcer.check_access(NetworkZone.COMPLIANCE, NetworkZone.TRADING) is False
    assert enforcer.check_access(NetworkZone.RISK, NetworkZone.PUBLIC) is False
    assert enforcer.check_access(NetworkZone.TRADING, NetworkZone.RESEARCH) is False


def test_network_telemetry_reporting(enforcer: NetworkIsolationEnforcer) -> None:
    enforcer.check_access(NetworkZone.TRADING, NetworkZone.RISK)
    enforcer.check_access(NetworkZone.PUBLIC, NetworkZone.TRADING)
    report = enforcer.get_report()
    assert report["cross_zone_traffic"] == 2
    assert report["denied_connections"] == 1
    assert report["violation_rate"] == 0.5
