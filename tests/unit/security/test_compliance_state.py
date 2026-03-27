import pytest

from qtrader.security.compliance_state import ComplianceStateEnforcer, SystemState


@pytest.fixture
def enforcer() -> ComplianceStateEnforcer:
    """Initialize a ComplianceStateEnforcer with industrial defaults."""
    # max_var=0.05 (5%), max_dd=0.15 (15%)
    return ComplianceStateEnforcer(max_var=0.05, max_dd=0.15)


def test_compliance_state_normal_operation(enforcer: ComplianceStateEnforcer) -> None:
    """Verify state remains NORMAL under healthy risk metrics."""
    # 1. Healthy state
    enforcer.update_state(var_score=0.01, current_dd=0.02)
    assert enforcer.current_state == SystemState.NORMAL  # noqa: S101


def test_compliance_state_halt_on_var_threshold(enforcer: ComplianceStateEnforcer) -> None:
    """Verify that exceeding VaR threshold immediately triggers HALTED state."""
    # VaR: 0.06 (Threshold: 0.05)
    enforcer.update_state(var_score=0.06, current_dd=0.02)
    assert enforcer.current_state == SystemState.HALTED  # noqa: S101

    report = enforcer.get_report()
    assert report["halt_events"] == 1  # noqa: S101


def test_compliance_state_breach_and_restricted_transitions(
    enforcer: ComplianceStateEnforcer,
) -> None:
    """Verify tiered transitions based on Max Drawdown metrics."""
    # 1. WARNING: 8% DD ( > 7.5% threshold for Warning at 50% max_dd)
    enforcer.update_state(var_score=0.02, current_dd=0.08)
    assert enforcer.current_state == SystemState.WARNING  # noqa: S101

    # 2. BREACH: 13% DD ( > 12.0% threshold for Breach at 80% max_dd)
    enforcer.update_state(var_score=0.02, current_dd=0.13)
    assert enforcer.current_state == SystemState.BREACH  # noqa: S101

    # 3. RESTRICTED: 16% DD ( > 15.0% threshold for Restricted)
    enforcer.update_state(var_score=0.02, current_dd=0.16)
    assert enforcer.current_state == SystemState.RESTRICTED  # noqa: S101


def test_compliance_state_denies_automated_recovery(enforcer: ComplianceStateEnforcer) -> None:
    """Verify that automated updates cannot recovery state from HALTED to NORMAL."""
    # 1. Enter HALTED state
    enforcer.update_state(var_score=0.10, current_dd=0.00)
    assert enforcer.current_state == SystemState.HALTED  # noqa: S101

    # 2. Metrics recover to normal
    enforcer.update_state(var_score=0.01, current_dd=0.01)
    # UNALTERED: HALTED state must be locked in for audit review.
    assert enforcer.current_state == SystemState.HALTED  # noqa: S101


def test_compliance_state_authorized_recovery_with_token(enforcer: ComplianceStateEnforcer) -> None:
    """Verify that recovery is granted with a valid HumanOverride Token."""
    # 1. System is HALTED
    enforcer.update_state(var_score=0.10, current_dd=0.20)

    # 2. Recovery attempt without token
    assert enforcer.request_recovery(SystemState.NORMAL, "INVALID_TOKEN") is False  # noqa: S101

    # 3. Recovery with industrial token
    assert enforcer.request_recovery(SystemState.NORMAL, "OVR_2026_03_RESTORE") is True  # noqa: S101
    assert enforcer.current_state == SystemState.NORMAL  # noqa: S101
