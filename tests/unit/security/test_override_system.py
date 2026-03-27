import time

import pytest

from qtrader.security.mfa import MultiFactorAuthenticator
from qtrader.security.override_system import HumanOverrideEnforcer
from qtrader.security.rbac import Role


@pytest.fixture
def mfa() -> MultiFactorAuthenticator:
    """Initialize a MultiFactorAuthenticator for the enforcer."""
    return MultiFactorAuthenticator(totp_window_s=30)


@pytest.fixture
def override(mfa: MultiFactorAuthenticator) -> HumanOverrideEnforcer:
    """Initialize a HumanOverrideEnforcer with an MFA engine."""
    return HumanOverrideEnforcer(mfa)


def test_override_valid_dual_approval(override: HumanOverrideEnforcer) -> None:
    """Verify that TRADER + RISK_MANAGER authorizes an override."""
    req_id = override.request_override("trader_01", "SELL_PROD_SENSITIVE", "Liquidity event")

    # 1. First Signature (TRADER)
    # Submission: Using correct simulated password/token baseline.
    assert override.submit_approval(req_id, "trader_01_alt", Role.TRADER, "123456") is True  # noqa: S101

    # 2. Second Signature (RISK_MANAGER)
    assert override.submit_approval(req_id, "risk_01", Role.RISK_MANAGER, "654321") is True  # noqa: S101

    # 3. Final Authorization Execution
    assert override.authorize(req_id) is True  # noqa: S101


def test_override_self_approval_violation(override: HumanOverrideEnforcer) -> None:
    """Verify rejection if the requester attempts to approve their own request."""
    # Requester: trader_01
    req_id = override.request_override("trader_01", "OVERRIDE_LIMIT", "Internal bypass")

    # Submission: TRADER trader_01 attempting to approve.
    assert override.submit_approval(req_id, "trader_01", Role.TRADER, "123456") is False  # noqa: S101


def test_override_role_overlap_violation(override: HumanOverrideEnforcer) -> None:
    """Verify rejection if two approvers share the same functional role (e.g. TRADER + TRADER)."""
    req_id = override.request_override("admin_01", "SYSTEM_HALT", "Maintenance")

    # 1. TRADER 1
    override.submit_approval(req_id, "trader_01", Role.TRADER, "111222")
    # 2. TRADER 2 (Role Overlap)
    override.submit_approval(req_id, "trader_02", Role.TRADER, "222333")

    # Final Authorization must fail due to role overlap (Exactly 2 distinct roles required).
    assert override.authorize(req_id) is False  # noqa: S101

    report = override.get_report()
    assert report["overrides_rejected"] == 1  # noqa: S101


def test_override_mfa_failure_rejection(override: HumanOverrideEnforcer) -> None:
    """Verify that a signature is rejected if MFA verification fails."""
    req_id = override.request_override("trader_01", "DEACTIVATE_FIREWALL", "Testing")

    # MFA Token: 000000 (Blocked logic in mfa.py)
    assert override.submit_approval(req_id, "risk_01", Role.RISK_MANAGER, "000000") is False  # noqa: S101


def test_override_temporal_integrity_expiration(override: HumanOverrideEnforcer) -> None:
    """Verify that an override is rejected 301 seconds after request (5m limit)."""
    # 1. Create Request
    req_id = override.request_override("trader_01", "FORCE_LIQUIDATION", "Emergency")

    # 2. Sign correctly
    override.submit_approval(req_id, "trader_01_alt", Role.TRADER, "111222")
    override.submit_approval(req_id, "risk_01", Role.RISK_MANAGER, "222333")

    # 3. Simulate clock shift beyond 300s
    override._requests[req_id].requested_at = time.time() - 301.0

    assert override.authorize(req_id) is False  # noqa: S101
    assert override.get_report()["overrides_rejected"] == 1  # noqa: S101
