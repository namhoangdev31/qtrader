import pytest

from qtrader.certification.checklist import ProductionChecklistValidator, ReadinessStatus


@pytest.fixture
def validator() -> ProductionChecklistValidator:
    """Initialize a ProductionChecklistValidator for institutional readiness."""
    return ProductionChecklistValidator()


def test_checklist_validator_full_readiness_pass(validator: ProductionChecklistValidator) -> None:
    """Verify that 100% check compliance results in a READY status."""
    system_state = {
        "services_up": True,
        "config_valid": True,
        "secrets_available": True,
        "risk_active": True,
        "monitoring_active": True,
    }

    artifact = validator.validate_readiness(system_state)

    assert artifact["ready"] is True
    assert artifact["readiness_state"] == ReadinessStatus.READY.name
    assert artifact["certification"]["failed_count"] == 0


def test_checklist_validator_partial_failure_blocking(
    validator: ProductionChecklistValidator,
) -> None:
    """Verify that a single service failure blocks readiness."""
    system_state = {
        "services_up": True,
        "config_valid": True,
        "secrets_available": True,
        "risk_active": False,  # FAILURE
        "monitoring_active": True,
    }

    artifact = validator.validate_readiness(system_state)

    assert artifact["ready"] is False
    assert artifact["readiness_state"] == ReadinessStatus.NOT_READY.name
    assert "risk_engine_active" in artifact["checklist"]
    assert artifact["checklist"]["risk_engine_active"] is False


def test_checklist_validator_failure_traceability(validator: ProductionChecklistValidator) -> None:
    """Verify that the readiness artifact identifies and indexes exactly which checks failed."""
    system_state = {
        "services_up": False,  # FAILURE 1
        "config_valid": False,  # FAILURE 2
        "secrets_available": True,
        "risk_active": True,
        "monitoring_active": True,
    }

    artifact = validator.validate_readiness(system_state)

    assert artifact["certification"]["failed_count"] == 2
    assert artifact["checklist"]["services_online"] is False
    assert artifact["checklist"]["config_valid"] is False


def test_checklist_validator_telemetry_tracking(
    validator: ProductionChecklistValidator,
) -> None:
    """Verify situational awareness for institutional deployment health."""
    validator.validate_readiness(
        {
            "services_up": True,
            "config_valid": True,
            "secrets_available": True,
            "risk_active": True,
            "monitoring_active": True,
        }
    )
    validator.validate_readiness({"services_up": False})  # Failure Case (5/5 failed)

    stats = validator.get_deployment_telemetry()
    assert stats["readiness_attempts"] == 2
    # 5 checks failed because ONLY 'services_up: False' was provided;
    # others default to False.
    assert stats["last_failed_check_count"] == 5
    assert stats["status"] == "DEPLOYMENT"
