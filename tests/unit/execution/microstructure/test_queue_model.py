from unittest.mock import MagicMock

import pytest

from qtrader.execution.microstructure.queue_model import QueuePositionModel


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with queue model parameters."""
    cfg = MagicMock()
    cfg.microstructure = {"queue_model": {"cancellation_coeff": 0.5, "default_intensity": 10.0}}
    return cfg


def test_queue_model_trade_depletion(execution_config: MagicMock) -> None:
    """Verify that trades directly deplete the virtual queue ahead."""
    model = QueuePositionModel(execution_config)

    # 100 volume ahead at T=1000
    vol_ahead = 100.0
    model.place_order(volume_ahead=vol_ahead, timestamp=1000.0)

    # Trade of 40 volume
    trade_vol = 40.0
    remaining = model.on_trade(trade_vol)
    expected_remaining = 60.0
    assert remaining == expected_remaining


def test_queue_model_stochastic_cancellations(execution_config: MagicMock) -> None:
    """Verify that cancellations deplete the queue stochastically."""
    model = QueuePositionModel(execution_config)

    # 50 volume ahead, 100 total volume at level
    vol_ahead = 50.0
    model.place_order(volume_ahead=vol_ahead, timestamp=1000.0)

    # Cancellation of 20 volume.
    # Total at level = 100. Ratio = 50/100 = 0.5.
    # Coeff = 0.5. Depletion = 20 * 0.5 * 0.5 = 5.0.
    total_volume = 100.0
    cancel_vol = 20.0
    model.on_cancellation(cancel_volume=cancel_vol, total_level_volume=total_volume - cancel_vol)

    expected_remaining = 45.0
    assert model._volume_ahead == expected_remaining


def test_queue_model_fill_probability(execution_config: MagicMock) -> None:
    """Verify fill probability increases over time and as queue depletes."""
    model = QueuePositionModel(execution_config)

    # Q=10, λ=10.
    vol_ahead = 10.0
    model.place_order(volume_ahead=vol_ahead, timestamp=1000.0)

    # T=0: P(fill) should be 0 (1-exp(0)=0)
    prob_t0 = model.estimate_fill_prob(1000.0)
    assert prob_t0 == 0.0

    # T=1s: P(fill) = 1 - e^(-10 * 1 / 10) = 1 - e^-1 = 0.632
    prob_t1 = model.estimate_fill_prob(2000.0)
    assert prob_t1 == pytest.approx(0.63212055)

    # If Q becomes 0, P(fill) should be 1.0
    model.on_trade(vol_ahead)
    assert model.estimate_fill_prob(2000.0) == 1.0


def test_queue_model_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify failsafe behavior for zero-volume or malformed states."""
    model = QueuePositionModel(execution_config)

    # 1. Zero volume ahead -> Probability 1
    model.place_order(0.0, 1000.0)
    assert model.estimate_fill_prob(2000.0) == 1.0

    # 2. Level vanishes (Total Volume -> 0)
    model.place_order(100.0, 1000.0)
    model.on_cancellation(100.0, 0.0)
    assert model._volume_ahead == 0.0

    # 3. Negative volume handling
    model.place_order(10.0, 1000.0)
    model.on_trade(100.0)
    assert model._volume_ahead == 0.0

    # 4. Malformed price/vol (None causing TypeError in math logic)
    # Must have non-zero volume ahead to hit the try block
    model.place_order(10.0, 1000.0)
    assert model.estimate_fill_prob(None) == 0.0  # type: ignore


def test_queue_model_reset(execution_config: MagicMock) -> None:
    """Verify state reset for industrial lifecycle management."""
    model = QueuePositionModel(execution_config)
    vol_ahead = 100.0
    model.place_order(vol_ahead, 1000.0)

    assert model._volume_ahead == vol_ahead
    model.reset()
    assert model._volume_ahead == 0.0
