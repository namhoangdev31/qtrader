import numpy as np
import pytest
from qtrader.ml.retrain_system import RetrainSystem


@pytest.fixture
def system() -> RetrainSystem:
    return RetrainSystem(psi_threshold=0.25, performance_drop_delta=0.15)


def test_psi_calculation_identical(system: RetrainSystem) -> None:
    expected = np.array([0.1, 0.2, 0.3, 0.4])
    actual = np.array([0.1, 0.2, 0.3, 0.4])
    psi = system.compute_psi(expected, actual)
    assert abs(psi) < 1e-06


def test_psi_calculation_drift(system: RetrainSystem) -> None:
    expected = np.array([0.1, 0.9])
    actual = np.array([0.9, 0.1])
    psi = system.compute_psi(expected, actual)
    assert psi > 3.0


def test_retrain_trigger_on_drift(system: RetrainSystem) -> None:
    expected = np.array([0.5, 0.5])
    actual = np.array([0.2, 0.8])
    decision = system.evaluate(expected, actual, current_perf=1.0, baseline_perf=1.0)
    assert decision.trigger is True
    assert "DATA_DRIFT" in decision.reason


def test_retrain_trigger_on_decay(system: RetrainSystem) -> None:
    expected = np.array([0.5, 0.5])
    actual = np.array([0.5, 0.5])
    decision = system.evaluate(expected, actual, current_perf=0.7, baseline_perf=0.9)
    assert decision.trigger is True
    assert "PERFORMANCE_DECAY" in decision.reason


def test_retrain_nominal_conditions(system: RetrainSystem) -> None:
    dist = np.array([0.5, 0.5])
    decision = system.evaluate(dist, dist, current_perf=0.95, baseline_perf=1.0)
    assert decision.trigger is False
    assert "NOMINAL" in decision.reason


def test_retrain_report_tracking(system: RetrainSystem) -> None:
    dist_ok = np.array([0.5, 0.5])
    dist_drift = np.array([0.1, 0.9])
    system.evaluate(dist_ok, dist_ok, 1.0, 1.0)
    system.evaluate(dist_ok, dist_drift, 1.0, 1.0)
    system.evaluate(dist_ok, dist_ok, 0.5, 1.0)
    report = system.get_retrain_report()
    assert report["total_triggers"] == 2
    assert report["peak_drift_psi"] > 0.0
