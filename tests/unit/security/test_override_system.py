import time
import pytest
from qtrader.security.mfa import MultiFactorAuthenticator
from qtrader.security.override_system import HumanOverrideEnforcer
from qtrader.security.rbac import Role


@pytest.fixture
def mfa() -> MultiFactorAuthenticator:
    return MultiFactorAuthenticator(totp_window_s=30)


@pytest.fixture
def override(mfa: MultiFactorAuthenticator) -> HumanOverrideEnforcer:
    return HumanOverrideEnforcer(mfa)


def test_override_valid_dual_approval(override: HumanOverrideEnforcer) -> None:
    req_id = override.request_override("trader_01", "SELL_PROD_SENSITIVE", "Liquidity event")
    assert override.submit_approval(req_id, "trader_01_alt", Role.TRADER, "123456") is True
    assert override.submit_approval(req_id, "risk_01", Role.RISK_MANAGER, "654321") is True
    assert override.authorize(req_id) is True


def test_override_self_approval_violation(override: HumanOverrideEnforcer) -> None:
    req_id = override.request_override("trader_01", "OVERRIDE_LIMIT", "Internal bypass")
    assert override.submit_approval(req_id, "trader_01", Role.TRADER, "123456") is False


def test_override_role_overlap_violation(override: HumanOverrideEnforcer) -> None:
    req_id = override.request_override("admin_01", "SYSTEM_HALT", "Maintenance")
    override.submit_approval(req_id, "trader_01", Role.TRADER, "111222")
    override.submit_approval(req_id, "trader_02", Role.TRADER, "222333")
    assert override.authorize(req_id) is False
    report = override.get_report()
    assert report["overrides_rejected"] == 1


def test_override_mfa_failure_rejection(override: HumanOverrideEnforcer) -> None:
    req_id = override.request_override("trader_01", "DEACTIVATE_FIREWALL", "Testing")
    assert override.submit_approval(req_id, "risk_01", Role.RISK_MANAGER, "000000") is False


def test_override_temporal_integrity_expiration(override: HumanOverrideEnforcer) -> None:
    req_id = override.request_override("trader_01", "FORCE_LIQUIDATION", "Emergency")
    override.submit_approval(req_id, "trader_01_alt", Role.TRADER, "111222")
    override.submit_approval(req_id, "risk_01", Role.RISK_MANAGER, "222333")
    override._requests[req_id].requested_at = time.time() - 301.0
    assert override.authorize(req_id) is False
    assert override.get_report()["overrides_rejected"] == 1
