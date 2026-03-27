import pytest

from qtrader.certification.stress_test import StrategyStressValidator, StressScenario


@pytest.fixture
def validator() -> StrategyStressValidator:
    """Initialize a StrategyStressValidator for institutional robustness certification."""
    return StrategyStressValidator(worst_case_loss_limit=0.1)


def test_strategy_stress_validator_robustness_pass(validator: StrategyStressValidator) -> None:
    """Verify that all stress PnLs within a 10% limit result in a PASS status."""
    scenario_results = {
        StressScenario.FLASH_CRASH: -0.05,
        StressScenario.VOLATILITY_SPIKE: -0.02,
        StressScenario.LIQUIDITY_DROP: -0.08,
        StressScenario.EXECUTION_DELAY: -0.01,
    }

    report = validator.run_stress_audit(scenario_results)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["metrics"]["worst_case_loss_percent"] == 0.08  # noqa: S101, PLR2004
    assert report["metrics"]["successful_scenario_count"] == 4  # noqa: S101, PLR2004


def test_strategy_stress_validator_worst_case_breach(validator: StrategyStressValidator) -> None:
    """Verify that a 15% loss (breach) in a single scenario results in a FAIL status."""
    scenario_results = {
        StressScenario.FLASH_CRASH: -0.15,  # BREACH (-15% < -10%)
        StressScenario.VOLATILITY_SPIKE: -0.05,
    }

    report = validator.run_stress_audit(scenario_results)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["scenario_breakdown"]["FLASH_CRASH"]["robustness_passed"] is False  # noqa: S101


def test_strategy_stress_validator_diversity_audit(validator: StrategyStressValidator) -> None:
    """Verify situational awareness and scenario failure tracking."""
    # Run 1: 1 failure
    validator.run_stress_audit({StressScenario.FLASH_CRASH: -0.20})
    # Run 2: 0 failures
    validator.run_stress_audit({StressScenario.VOLATILITY_SPIKE: -0.02})

    stats = validator.get_stress_telemetry()
    assert stats["cumulative_scenario_failures"] == 1  # noqa: S101
    assert stats["peak_stress_loss_observed"] == 0.2  # noqa: S101, PLR2004
    assert stats["status"] == "STRESS_HEALTH"  # noqa: S101


def test_strategy_stress_validator_artifact_integrity(validator: StrategyStressValidator) -> None:
    """Verify that the stress test artifact includes structural performance metadata."""
    report = validator.run_stress_audit({StressScenario.LIQUIDITY_DROP: -0.09})

    assert "scenario_breakdown" in report  # noqa: S101
    assert "worst_case_loss_percent" in report["metrics"]  # noqa: S101
    assert report["certification"]["institutional_loss_limit"] == 0.1  # noqa: S101, PLR2004
