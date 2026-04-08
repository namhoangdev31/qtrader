import numpy as np
import pytest

from qtrader.ml.retrain_system import RetrainSystem


@pytest.fixture
def system() -> RetrainSystem:
    """Initialize RetrainSystem with industrial defaults (PSI 0.25)."""
    return RetrainSystem(psi_threshold=0.25, performance_drop_delta=0.15)


def test_psi_calculation_identical(system: RetrainSystem) -> None:
    """Verify that identical distributions yield 0.0 PSI."""
    expected = np.array([0.1, 0.2, 0.3, 0.4])
    actual = np.array([0.1, 0.2, 0.3, 0.4])
    psi = system.compute_psi(expected, actual)
    assert abs(psi) < 1e-6


def test_psi_calculation_drift(system: RetrainSystem) -> None:
    """Verify PSI calculation for shifted distributions."""
    # Drastic shift: [0.1, 0.9] -> [0.9, 0.1]
    expected = np.array([0.1, 0.9])
    actual = np.array([0.9, 0.1])

    # PSI = (0.1 - 0.9) * ln(0.1 / 0.9) + (0.9 - 0.1) * ln(0.9 / 0.1)
    # PSI = -0.8 * -2.197 + 0.8 * 2.197 = 1.7576 + 1.7576 = 3.515
    psi = system.compute_psi(expected, actual)
    assert psi > 3.0


def test_retrain_trigger_on_drift(system: RetrainSystem) -> None:
    """Verify that significant drift (PSI > 0.25) authorizes a trigger."""
    expected = np.array([0.5, 0.5])
    actual = np.array([0.2, 0.8])  # Moderate drift

    # PSI ~ (0.5-0.2)*log(0.5/0.2) + (0.5-0.8)*log(0.5/0.8)
    # PSI ~ 0.3 * 0.916 + -0.3 * -0.47 = 0.27 + 0.14 = 0.41 > 0.25

    decision = system.evaluate(expected, actual, current_perf=1.0, baseline_perf=1.0)
    assert decision.trigger is True
    assert "DATA_DRIFT" in decision.reason


def test_retrain_trigger_on_decay(system: RetrainSystem) -> None:
    """Verify that performance decay triggers retraining even with 0 PSI."""
    expected = np.array([0.5, 0.5])
    actual = np.array([0.5, 0.5])

    # Decay: 0.9 -> 0.7 (Drop=0.2 > 0.15)
    decision = system.evaluate(expected, actual, current_perf=0.7, baseline_perf=0.9)
    assert decision.trigger is True
    assert "PERFORMANCE_DECAY" in decision.reason


def test_retrain_nominal_conditions(system: RetrainSystem) -> None:
    """Verify that stable conditions do not trigger retraining."""
    dist = np.array([0.5, 0.5])

    # Baseline 1.0 -> Current 0.95 (Drop=0.05 < 0.15)
    decision = system.evaluate(dist, dist, current_perf=0.95, baseline_perf=1.0)
    assert decision.trigger is False
    assert "NOMINAL" in decision.reason


def test_retrain_report_tracking(system: RetrainSystem) -> None:
    """Verify situational awareness telemetry tracking."""
    dist_ok = np.array([0.5, 0.5])
    dist_drift = np.array([0.1, 0.9])

    # 1. OK
    system.evaluate(dist_ok, dist_ok, 1.0, 1.0)
    # 2. DRIFT -> Trigger
    system.evaluate(dist_ok, dist_drift, 1.0, 1.0)
    # 3. DECAY -> Trigger
    system.evaluate(dist_ok, dist_ok, 0.5, 1.0)

    report = system.get_retrain_report()
    assert report["total_triggers"] == 2
    assert report["peak_drift_psi"] > 0.0
