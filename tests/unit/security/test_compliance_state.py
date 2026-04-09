import pytest
from qtrader.security.compliance_state import ComplianceStateEnforcer, SystemState


@pytest.fixture
def enforcer() -> ComplianceStateEnforcer:
    return ComplianceStateEnforcer(max_var=0.05, max_dd=0.15)


def test_compliance_state_normal_operation(enforcer: ComplianceStateEnforcer) -> None:
    enforcer.update_state(var_score=0.01, current_dd=0.02)
    assert enforcer.current_state == SystemState.NORMAL


def test_compliance_state_halt_on_var_threshold(enforcer: ComplianceStateEnforcer) -> None:
    enforcer.update_state(var_score=0.06, current_dd=0.02)
    assert enforcer.current_state == SystemState.HALTED
    report = enforcer.get_report()
    assert report["halt_events"] == 1


def test_compliance_state_breach_and_restricted_transitions(
    enforcer: ComplianceStateEnforcer,
) -> None:
    enforcer.update_state(var_score=0.02, current_dd=0.08)
    assert enforcer.current_state == SystemState.WARNING
    enforcer.update_state(var_score=0.02, current_dd=0.13)
    assert enforcer.current_state == SystemState.BREACH
    enforcer.update_state(var_score=0.02, current_dd=0.16)
    assert enforcer.current_state == SystemState.RESTRICTED


def test_compliance_state_denies_automated_recovery(enforcer: ComplianceStateEnforcer) -> None:
    enforcer.update_state(var_score=0.1, current_dd=0.0)
    assert enforcer.current_state == SystemState.HALTED
    enforcer.update_state(var_score=0.01, current_dd=0.01)
    assert enforcer.current_state == SystemState.HALTED


def test_compliance_state_authorized_recovery_with_token(enforcer: ComplianceStateEnforcer) -> None:
    enforcer.update_state(var_score=0.1, current_dd=0.2)
    assert enforcer.request_recovery(SystemState.NORMAL, "INVALID_TOKEN") is False
    assert enforcer.request_recovery(SystemState.NORMAL, "OVR_2026_03_RESTORE") is True
    assert enforcer.current_state == SystemState.NORMAL
