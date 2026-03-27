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

    assert artifact["ready"] is True  # noqa: S101
    assert artifact["readiness_state"] == ReadinessStatus.READY.name  # noqa: S101
    assert artifact["certification"]["failed_count"] == 0  # noqa: S101


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

    assert artifact["ready"] is False  # noqa: S101
    assert artifact["readiness_state"] == ReadinessStatus.NOT_READY.name  # noqa: S101
    assert "risk_engine_active" in artifact["checklist"]  # noqa: S101
    assert artifact["checklist"]["risk_engine_active"] is False  # noqa: S101


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

    assert artifact["certification"]["failed_count"] == 2  # noqa: S101, PLR2004
    assert artifact["checklist"]["services_online"] is False  # noqa: S101
    assert artifact["checklist"]["config_valid"] is False  # noqa: S101


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
    assert stats["readiness_attempts"] == 2  # noqa: S101, PLR2004
    # 5 checks failed because ONLY 'services_up: False' was provided;
    # others default to False.
    assert stats["last_failed_check_count"] == 5  # noqa: S101, PLR2004
    assert stats["status"] == "DEPLOYMENT"  # noqa: S101
