import pytest

from qtrader.certification.risk_simulation import RiskStressValidator, StressScenario


@pytest.fixture
def validator() -> RiskStressValidator:
    """Initialize a RiskStressValidator for institutional defensive certification."""
    return RiskStressValidator(primary_risk_limit=0.1)


def test_risk_stress_validator_breach_halt_pass(validator: RiskStressValidator) -> None:
    """Verify that a 0.15 drawdown spike (breach) result in a CORRECT status and HALTED state."""
    report = validator.run_stress_test(
        scenario=StressScenario.SUDDEN_DRAWDOWN,
        simulated_risk_value=0.15,  # Exceeds 0.1
        detection_latency_ms=250.0,  # Under 1s
    )

    assert report["result"] == "CORRECT"
    assert report["metrics"]["breach_triggered"] is True
    assert report["metrics"]["terminal_system_state"] == "HALTED"


def test_risk_stress_validator_latency_threshold_fail(validator: RiskStressValidator) -> None:
    """Verify that a response exceeding 1s results in a FAIL status."""
    report = validator.run_stress_test(
        scenario=StressScenario.VOLATILITY_EXPLOSION,
        simulated_risk_value=0.20,
        detection_latency_ms=1500.0,  # Exceeds 1s
    )

    assert report["result"] == "FAIL"


def test_risk_stress_validator_non_breach_continuity(validator: RiskStressValidator) -> None:
    """Verify that risk metrics within limits (e.g., 0.05) result in state OPEN."""
    report = validator.run_stress_test(
        scenario=StressScenario.SUDDEN_DRAWDOWN,
        simulated_risk_value=0.05,  # Within limits
        detection_latency_ms=10.0,
    )

    assert report["result"] == "CORRECT"
    assert report["metrics"]["breach_triggered"] is False
    assert report["metrics"]["terminal_system_state"] == "OPEN"


def test_risk_stress_validator_defensive_telemetry(validator: RiskStressValidator) -> None:
    """Verify situational awareness and incorrect response tracking."""
    validator.run_stress_test(
        StressScenario.SUDDEN_DRAWDOWN,
        simulated_risk_value=0.15,
        detection_latency_ms=0.1,
    )
    validator.run_stress_test(
        StressScenario.LIQUIDITY_COLLAPSE,
        simulated_risk_value=0.15,
        detection_latency_ms=2000.0,
    )

    stats = validator.get_defensive_telemetry()
    assert stats["lifecycle_stresses"] == 2
    assert stats["incorrect_response_count"] == 1
    assert stats["status"] == "DEFENSIVE_CERTIFICATION"


def test_risk_stress_validator_artifact_integrity(validator: RiskStressValidator) -> None:
    """Verify that the risk test artifact includes structural performance metadata."""
    report = validator.run_stress_test(StressScenario.LIQUIDITY_COLLAPSE, simulated_risk_value=0.3)

    assert "scenario" in report["certification"]
    assert report["certification"]["scenario"] == "LIQUIDITY_COLLAPSE"
    assert "real_sim_duration_ms" in report["certification"]
