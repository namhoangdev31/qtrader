from unittest.mock import MagicMock

import pytest

from qtrader.execution.microstructure.toxic_flow import ToxicFlowPredictor


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with toxic flow parameters."""
    cfg = MagicMock()
    cfg.microstructure = {"toxic_flow": {"window_size": 20, "threshold": 0.7}}
    return cfg


def test_toxic_flow_informed_scenario(execution_config: MagicMock) -> None:
    """Verify that informed flow (consistent direction) results in high toxicity score."""
    predictor = ToxicFlowPredictor(execution_config)

    # 100% of Buys followed by +0.1% move. Highly Toxic.
    last_score = 0.5
    for _ in range(15):
        last_score = predictor.update(trade_side=1, price_move=0.001)

    # τ > 0.8 (Close to 1.0)
    high_threshold = 0.8
    assert last_score > high_threshold  # noqa: S101
    assert last_score == pytest.approx(1.0)  # noqa: S101


def test_toxic_flow_noise_scenario(execution_config: MagicMock) -> None:
    """Verify that random noise results in neutral toxicity score (around 0.5)."""
    predictor = ToxicFlowPredictor(execution_config)

    # Randomly alternate direction and impact such that they don't correlate
    # Window = 20. Need > 10 samples.
    for i in range(20):
        side = 1 if i % 2 == 0 else -1
        # Move is always positive, so half correlate, half anti-correlate
        move = 0.001
        score = predictor.update(side, move)

    # τ should be close to 0.5
    neutral = 0.5
    assert score == pytest.approx(neutral)  # noqa: S101


def test_toxic_flow_mean_reverting_scenario(execution_config: MagicMock) -> None:
    """Verify that mean-reverting flow results in low toxicity score (below 0.5)."""
    predictor = ToxicFlowPredictor(execution_config)

    # Buy followed by price DROP (uninformed/market-making)
    last_score = 0.5
    for _ in range(15):
        last_score = predictor.update(trade_side=1, price_move=-0.001)

    # τ < 0.2 (Close to 0.0)
    low_threshold = 0.2
    assert last_score < low_threshold  # noqa: S101
    assert last_score == pytest.approx(0.0)  # noqa: S101


def test_toxic_flow_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify industrial safety and failsafe behavior."""
    predictor = ToxicFlowPredictor(execution_config)
    neutral = 0.5

    # 1. Zero denominator (no price moves)
    # Window needs 10 samples before it computes
    for _ in range(10):
        predictor.update(1, 0.0)
    assert predictor.update(1, 0.0) == neutral  # noqa: S101

    # 2. Insufficient samples
    predictor.reset()
    for _ in range(5):
        score = predictor.update(1, 0.001)
    assert score == neutral  # noqa: S101

    # 3. Malformed inputs (None causing TypeError in math logic)
    # This should trigger the exception block in update()
    assert predictor.update(None, 0.001) == neutral  # type: ignore # noqa: S101


def test_toxic_flow_reset(execution_config: MagicMock) -> None:
    """Verify state reset for industrial lifecycle management."""
    predictor = ToxicFlowPredictor(execution_config)
    predictor.update(1, 0.001)

    assert len(predictor._history) > 0  # noqa: S101
    predictor.reset()
    assert len(predictor._history) == 0  # noqa: S101
