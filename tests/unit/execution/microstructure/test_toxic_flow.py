from unittest.mock import MagicMock
import pytest
from qtrader.execution.microstructure.toxic_flow import ToxicFlowPredictor


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.microstructure = {"toxic_flow": {"window_size": 20, "threshold": 0.7}}
    return cfg


def test_toxic_flow_informed_scenario(execution_config: MagicMock) -> None:
    predictor = ToxicFlowPredictor(execution_config)
    last_score = 0.5
    for _ in range(15):
        last_score = predictor.update(trade_side=1, price_move=0.001)
    high_threshold = 0.8
    assert last_score > high_threshold
    assert last_score == pytest.approx(1.0)


def test_toxic_flow_noise_scenario(execution_config: MagicMock) -> None:
    predictor = ToxicFlowPredictor(execution_config)
    for i in range(20):
        side = 1 if i % 2 == 0 else -1
        move = 0.001
        score = predictor.update(side, move)
    neutral = 0.5
    assert score == pytest.approx(neutral)


def test_toxic_flow_mean_reverting_scenario(execution_config: MagicMock) -> None:
    predictor = ToxicFlowPredictor(execution_config)
    last_score = 0.5
    for _ in range(15):
        last_score = predictor.update(trade_side=1, price_move=-0.001)
    low_threshold = 0.2
    assert last_score < low_threshold
    assert last_score == pytest.approx(0.0)


def test_toxic_flow_catastrophic_safety(execution_config: MagicMock) -> None:
    predictor = ToxicFlowPredictor(execution_config)
    neutral = 0.5
    for _ in range(10):
        predictor.update(1, 0.0)
    assert predictor.update(1, 0.0) == neutral
    predictor.reset()
    for _ in range(5):
        score = predictor.update(1, 0.001)
    assert score == neutral
    assert predictor.update(None, 0.001) == neutral


def test_toxic_flow_reset(execution_config: MagicMock) -> None:
    predictor = ToxicFlowPredictor(execution_config)
    predictor.update(1, 0.001)
    assert len(predictor._history) > 0
    predictor.reset()
    assert len(predictor._history) == 0
