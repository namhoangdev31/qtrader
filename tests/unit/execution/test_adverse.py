import math

import polars as pl
import pytest

from qtrader.execution.adverse_model import AdverseModelParams, AdverseSelectionModel

# Constants for verification
SIGMOID_ZERO = 0.5
SIGMOID_ONE = 1.0
SIGMOID_NEUTRAL = 0.0


def test_sigmoid() -> None:
    """Verify sigmoid math and edge cases."""
    model = AdverseSelectionModel()

    assert model.sigmoid(0.0) == SIGMOID_ZERO
    assert model.sigmoid(100.0) == SIGMOID_ONE
    assert model.sigmoid(-100.0) == pytest.approx(0.0, abs=1e-10)

    # Test range [0, 1]
    for x in range(-10, 11):
        p = model.sigmoid(float(x))
        assert 0.0 <= p <= 1.0


def test_estimate_probability() -> None:
    """Verify probability estimation logic."""
    alpha, beta, gamma, intercept = 2.0, 1.0, 0.5, -1.0
    params = AdverseModelParams(alpha=alpha, beta=beta, gamma=gamma, intercept=intercept)
    model = AdverseSelectionModel(params=params)

    # Positive case
    # Score = 2.0 * 1.0 + 1.0 * 0.5 + 0.5 * 1.0 - 1.0 = 2.0 + 0.5 + 0.5 - 1.0 = 2.0
    # P = sigmoid(2.0) = 1 / (1 + exp(-2.0))
    p = model.estimate_probability(imbalance=1.0, delta_p=0.5, fill_rate=1.0)
    expected = 1.0 / (1.0 + math.exp(-2.0))
    assert p == pytest.approx(expected)

    # Bounded in [0, 1]
    assert 0.0 <= p <= 1.0


def test_probability_increases_with_imbalance() -> None:
    """Verify that probability increases with imbalance (positive alpha)."""
    model = AdverseSelectionModel(AdverseModelParams(alpha=1.0))

    p_low = model.estimate_probability(imbalance=-1.0, delta_p=0.0, fill_rate=0.0)
    p_high = model.estimate_probability(imbalance=1.0, delta_p=0.0, fill_rate=0.0)

    assert p_high > p_low


def test_estimate_batch() -> None:
    """Verify vectorized batch estimation."""
    params = AdverseModelParams(alpha=1.0, beta=1.0, gamma=0.0, intercept=0.0)
    model = AdverseSelectionModel(params=params)

    df = pl.DataFrame(
        {"imbalance": [0.0, 1.0, -1.0], "delta_p": [0.0, 0.0, 1.0], "fill_rate": [0.5, 0.5, 0.5]}
    )

    result = model.estimate_batch(df)

    # Sample checks
    assert result["p_adverse"][0] == SIGMOID_ZERO
    assert result["p_adverse"][1] == pytest.approx(1.0 / (1.0 + math.exp(-1.0)))
    assert result["p_adverse"][2] == SIGMOID_ZERO  # sigmoid(-1 + 1 + 0) = 0.5


def test_default_params() -> None:
    """Verify model initialization with default parameters."""
    model = AdverseSelectionModel()
    assert model.params.alpha == 1.0
    assert model.params.beta == 1.0
    assert model.params.gamma == 1.0
    assert model.params.intercept == 0.0
