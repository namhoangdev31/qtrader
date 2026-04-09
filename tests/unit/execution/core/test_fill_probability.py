from unittest.mock import MagicMock
import pytest
from qtrader.execution.core.fill_probability import FillProbabilityModel


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.microstructure = {"queue_model": {"default_intensity": 10.0}}
    return cfg


def test_fill_probability_intensity_sensitivity(execution_config: MagicMock) -> None:
    model = FillProbabilityModel(execution_config)
    prob_low = model.compute(intensity=1.0, time_horizon=1.0, queue_pos=100.0)
    prob_high = model.compute(intensity=50.0, time_horizon=1.0, queue_pos=100.0)
    assert 0.0 < prob_low < prob_high < 1.0
    assert prob_high > prob_low


def test_fill_probability_queue_sensitivity(execution_config: MagicMock) -> None:
    model = FillProbabilityModel(execution_config)
    prob_small = model.compute(intensity=10.0, time_horizon=1.0, queue_pos=10.0)
    prob_large = model.compute(intensity=10.0, time_horizon=1.0, queue_pos=1000.0)
    assert 0.0 < prob_large < prob_small <= 1.0
    assert prob_small > prob_large


def test_fill_probability_time_sensitivity(execution_config: MagicMock) -> None:
    model = FillProbabilityModel(execution_config)
    prob_now = model.compute(intensity=10.0, time_horizon=1.0, queue_pos=100.0)
    prob_later = model.compute(intensity=10.0, time_horizon=60.0, queue_pos=100.0)
    assert prob_later > prob_now


def test_fill_probability_boundary_conditions(execution_config: MagicMock) -> None:
    model = FillProbabilityModel(execution_config)
    assert model.compute(intensity=10.0, time_horizon=1.0, queue_pos=0.0) == 1.0
    assert model.compute(intensity=10.0, time_horizon=0.0, queue_pos=100.0) == 0.0
    assert model.compute(intensity=10000000000.0, time_horizon=10000000000.0, queue_pos=1.0) == 1.0
    assert model.compute(intensity=None, time_horizon=1.0, queue_pos=None) > 0.0


def test_fill_probability_catastrophic_safety(execution_config: MagicMock) -> None:
    model = FillProbabilityModel(execution_config)
    assert model.compute(intensity=-10.0, time_horizon=1.0, queue_pos=100.0) == 0.0
    assert model.compute(intensity=10.0, time_horizon=1.0, queue_pos="INVALID") == 0.0
