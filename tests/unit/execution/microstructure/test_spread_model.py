from statistics import StatisticsError
from unittest import mock
import pytest
from qtrader.execution.microstructure.spread_model import SpreadDynamicsModel


@pytest.fixture
def execution_config() -> mock.MagicMock:
    cfg = mock.MagicMock()
    cfg.microstructure = {"spread_model": {"window_size": 10, "alpha": 0.5, "beta": 0.05}}
    return cfg


def test_spread_model_volatility_widening(execution_config: mock.MagicMock) -> None:
    model = SpreadDynamicsModel(execution_config)
    current_spread = 0.01
    last_pred = 0.0
    for _ in range(5):
        last_pred = model.update(bid=100.0, ask=100.01, volume=0.0)
    assert last_pred == pytest.approx(current_spread)
    model.update(bid=90.0, ask=90.01, volume=0.0)
    pred_spread = model.update(bid=110.0, ask=110.01, volume=0.0)
    assert pred_spread > current_spread


def test_spread_model_liquidity_tightening(execution_config: mock.MagicMock) -> None:
    model = SpreadDynamicsModel(execution_config)
    for _ in range(5):
        model.update(bid=100.0, ask=100.01, volume=0.0)
    pred_spread = model.update(bid=100.0, ask=100.01, volume=1.0)
    min_spread = 1e-08
    assert pred_spread == pytest.approx(min_spread)


def test_spread_model_catastrophic_safety(execution_config: mock.MagicMock) -> None:
    model = SpreadDynamicsModel(execution_config)
    assert model.update(100.0, 100.01, 0.0) == pytest.approx(0.01)
    for _ in range(5):
        model.update(100.0, 100.01, 0.0)
    pred = model.update(100.0, 101.0, 0.0)
    assert pred >= 1.0
    model.reset()
    model.update(100.0, 100.01, 10.0)
    assert model.update(None, 100.01, 10.0) == pytest.approx(0.01)


def test_spread_model_statistics_failure(execution_config: mock.MagicMock) -> None:
    model = SpreadDynamicsModel(execution_config)
    with mock.patch("statistics.stdev", side_effect=StatisticsError):
        for _ in range(5):
            model.update(100.0, 100.01, 0.0)
        assert model.update(100.0, 100.01, 0.0) == pytest.approx(0.01)


def test_spread_model_reset(execution_config: mock.MagicMock) -> None:
    model = SpreadDynamicsModel(execution_config)
    model.update(100.0, 100.01, 10.0)
    assert len(model._mid_prices) > 0
    model.reset()
    assert len(model._mid_prices) == 0
