from unittest.mock import MagicMock

import pytest

from qtrader.execution.core.fill_probability import FillProbabilityModel


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with probability parameters."""
    cfg = MagicMock()
    # Path configuration alignment
    cfg.microstructure = {
        "queue_model": {
            "default_intensity": 10.0
        }
    }
    return cfg


def test_fill_probability_intensity_sensitivity(execution_config: MagicMock) -> None:
    """Verify that probability increases with higher trade intensity."""
    model = FillProbabilityModel(execution_config)
    
    # Low intensity (1 trade/sec) vs High intensity (50 trades/sec)
    # Q = 100, t = 1.0
    prob_low = model.compute(intensity=1.0, time_horizon=1.0, queue_pos=100.0)
    prob_high = model.compute(intensity=50.0, time_horizon=1.0, queue_pos=100.0)
    
    assert 0.0 < prob_low < prob_high < 1.0
    assert prob_high > prob_low


def test_fill_probability_queue_sensitivity(execution_config: MagicMock) -> None:
    """Verify that probability decreases as queue volume ahead increases."""
    model = FillProbabilityModel(execution_config)
    
    # Small Queue (10) vs Large Queue (1000)
    # lambda = 10.0, t = 1.0
    prob_small = model.compute(intensity=10.0, time_horizon=1.0, queue_pos=10.0)
    prob_large = model.compute(intensity=10.0, time_horizon=1.0, queue_pos=1000.0)
    
    assert 0.0 < prob_large < prob_small <= 1.0
    assert prob_small > prob_large


def test_fill_probability_time_sensitivity(execution_config: MagicMock) -> None:
    """Verify that probability increases with longer time horizons."""
    model = FillProbabilityModel(execution_config)
    
    # 1 second horizon vs 60 second horizon
    prob_now = model.compute(intensity=10.0, time_horizon=1.0, queue_pos=100.0)
    prob_later = model.compute(intensity=10.0, time_horizon=60.0, queue_pos=100.0)
    
    assert prob_later > prob_now


def test_fill_probability_boundary_conditions(execution_config: MagicMock) -> None:
    """Verify safety logic for zero-queue, zero-time, and overflow scenarios."""
    model = FillProbabilityModel(execution_config)
    
    # 1. Zero Queue: Should be instant fill
    assert model.compute(intensity=10.0, time_horizon=1.0, queue_pos=0.0) == 1.0
    
    # 2. Zero Time: Should be impossible fill
    assert model.compute(intensity=10.0, time_horizon=0.0, queue_pos=100.0) == 0.0
    
    # 3. Very Large Request (Overflow): Should be near certain fill
    assert model.compute(intensity=1e10, time_horizon=1e10, queue_pos=1.0) == 1.0
    
    # 4. Default Fallback
    assert model.compute(intensity=None, time_horizon=1.0, queue_pos=None) > 0.0


def test_fill_probability_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify that the model handles malformed data silently."""
    model = FillProbabilityModel(execution_config)
    
    # 1. Negative inputs
    assert model.compute(intensity=-10.0, time_horizon=1.0, queue_pos=100.0) == 0.0
    
    # 2. Malformed objects (should hit Exception block)
    # Passing a string as queue_pos
    assert model.compute(intensity=10.0, time_horizon=1.0, queue_pos="INVALID") == 0.0  # type: ignore
