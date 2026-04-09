from unittest.mock import MagicMock
import pytest
from qtrader.execution.microstructure.queue_model import QueuePositionModel


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.microstructure = {"queue_model": {"cancellation_coeff": 0.5, "default_intensity": 10.0}}
    return cfg


def test_queue_model_trade_depletion(execution_config: MagicMock) -> None:
    model = QueuePositionModel(execution_config)
    vol_ahead = 100.0
    model.place_order(volume_ahead=vol_ahead, timestamp=1000.0)
    trade_vol = 40.0
    remaining = model.on_trade(trade_vol)
    expected_remaining = 60.0
    assert remaining == expected_remaining


def test_queue_model_stochastic_cancellations(execution_config: MagicMock) -> None:
    model = QueuePositionModel(execution_config)
    vol_ahead = 50.0
    model.place_order(volume_ahead=vol_ahead, timestamp=1000.0)
    total_volume = 100.0
    cancel_vol = 20.0
    model.on_cancellation(cancel_volume=cancel_vol, total_level_volume=total_volume - cancel_vol)
    expected_remaining = 45.0
    assert model._volume_ahead == expected_remaining


def test_queue_model_fill_probability(execution_config: MagicMock) -> None:
    model = QueuePositionModel(execution_config)
    vol_ahead = 10.0
    model.place_order(volume_ahead=vol_ahead, timestamp=1000.0)
    prob_t0 = model.estimate_fill_prob(1000.0)
    assert prob_t0 == 0.0
    prob_t1 = model.estimate_fill_prob(2000.0)
    assert prob_t1 == pytest.approx(0.63212055)
    model.on_trade(vol_ahead)
    assert model.estimate_fill_prob(2000.0) == 1.0


def test_queue_model_catastrophic_safety(execution_config: MagicMock) -> None:
    model = QueuePositionModel(execution_config)
    model.place_order(0.0, 1000.0)
    assert model.estimate_fill_prob(2000.0) == 1.0
    model.place_order(100.0, 1000.0)
    model.on_cancellation(100.0, 0.0)
    assert model._volume_ahead == 0.0
    model.place_order(10.0, 1000.0)
    model.on_trade(100.0)
    assert model._volume_ahead == 0.0
    model.place_order(10.0, 1000.0)
    assert model.estimate_fill_prob(None) == 0.0


def test_queue_model_reset(execution_config: MagicMock) -> None:
    model = QueuePositionModel(execution_config)
    vol_ahead = 100.0
    model.place_order(vol_ahead, 1000.0)
    assert model._volume_ahead == vol_ahead
    model.reset()
    assert model._volume_ahead == 0.0
