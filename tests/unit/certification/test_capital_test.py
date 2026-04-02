import pytest

from qtrader.certification.capital_test import CapitalPreservationValidator, SolvencyScenario


@pytest.fixture
def validator() -> CapitalPreservationValidator:
    """Initialize a CapitalPreservationValidator for institutional solvency certification."""
    return CapitalPreservationValidator(max_loss_threshold_percent=0.15)


def test_capital_validator_safe_preservation_pass(validator: CapitalPreservationValidator) -> None:
    """Verify that a 12% max loss within a 15% limit results in a PASS status."""
    initial = 1_000_000.0
    current = 880_000.0  # 12% loss

    report = validator.validate_preservation(
        initial_capital=initial,
        current_capital=current,
        scenario=SolvencyScenario.CONTINUOUS_LOSSES,
    )

    assert report["result"] == "PASS"
    assert report["metrics"]["percentage_depletion"] == 0.12
    assert report["metrics"]["gating_violated"] is False


def test_capital_validator_solvency_breach_fail(validator: CapitalPreservationValidator) -> None:
    """Verify that a 20% loss spike exceeds the 15% limit and results in a FAIL status."""
    initial = 1_000_000.0
    current = 800_000.0  # 20% loss

    report = validator.validate_preservation(
        initial_capital=initial, current_capital=current, scenario=SolvencyScenario.FLASH_CRASH
    )

    assert report["result"] == "FAIL"
    assert report["metrics"]["gating_violated"] is True


def test_capital_validator_slippage_spike_pass(validator: CapitalPreservationValidator) -> None:
    """Verify that slippage spikes within solvency bounds result in a PASS status."""
    initial = 100_000.0
    current = 95_000.0  # 5% loss

    report = validator.validate_preservation(
        initial_capital=initial, current_capital=current, scenario=SolvencyScenario.SLIPPAGE_SPIKE
    )

    assert report["result"] == "PASS"


def test_capital_validator_solvency_telemetry(validator: CapitalPreservationValidator) -> None:
    """Verify situational awareness and cumulative peak drawdown tracking."""
    validator.validate_preservation(100.0, 95.0, SolvencyScenario.SLIPPAGE_SPIKE)  # 5%
    validator.validate_preservation(100.0, 90.0, SolvencyScenario.FLASH_CRASH)  # 10%
    validator.validate_preservation(100.0, 80.0, SolvencyScenario.CONTINUOUS_LOSSES)  # 20% (Breach)

    stats = validator.get_solvency_telemetry()
    assert stats["peak_drawdown_observed"] == 0.2
    assert stats["worst_case_loss"] == 0.2
    assert stats["status"] == "CAPITAL_SOLVENCY"


def test_capital_validator_artifact_integrity(validator: CapitalPreservationValidator) -> None:
    """Verify that the capital test artifact includes structural performance metadata."""
    report = validator.validate_preservation(1000.0, 900.0, SolvencyScenario.FLASH_CRASH)

    assert "scenario" in report["certification"]
    assert report["certification"]["scenario"] == "FLASH_CRASH"
    assert "real_sim_duration_ms" in report["certification"]
