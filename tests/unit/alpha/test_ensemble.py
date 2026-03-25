import polars as pl
import pytest

from qtrader.alpha.ensemble_model import AlphaEnsemble

# ──────────────────────────────────────────────
# Constants (PLR2004)
# ──────────────────────────────────────────────
TEST_TOLERANCE = 1e-6
SUM_TARGET = 1.0
FALLBACK_WEIGHT = 0.5
WEIGHT_A_EXPECTED = 2.0 / 3.0
WEIGHT_B_EXPECTED = 1.0 / 3.0


def test_calculate_weights_basic() -> None:
    """Verify weights for signals with different IC and volatility."""
    # Signal A: IC=0.04, Vol=0.02 -> Score=2.0
    # Signal B: IC=0.02, Vol=0.02 -> Score=1.0
    # Total Score = 3.0 -> wA=2/3, wB=1/3
    metrics = {"alpha_a": {"ic": 0.04, "std": 0.02}, "alpha_b": {"ic": 0.02, "std": 0.02}}

    weights = AlphaEnsemble.calculate_weights(metrics)

    assert abs(weights["alpha_a"] - WEIGHT_A_EXPECTED) < TEST_TOLERANCE
    assert abs(weights["alpha_b"] - WEIGHT_B_EXPECTED) < TEST_TOLERANCE
    assert abs(sum(weights.values()) - SUM_TARGET) < TEST_TOLERANCE


def test_calculate_weights_fallback() -> None:
    """Verify equal weighting when all performance is zero."""
    metrics = {"alpha_a": {"ic": 0.0, "std": 0.1}, "alpha_b": {"ic": 0.0, "std": 0.1}}
    weights = AlphaEnsemble.calculate_weights(metrics)
    assert weights["alpha_a"] == FALLBACK_WEIGHT
    assert weights["alpha_b"] == FALLBACK_WEIGHT


def test_combine_signals() -> None:
    """Verify weighted sum of signals."""
    df = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": [0.0, 1.0, 2.0]})
    weights = {"a": 0.6, "b": 0.4}

    ensemble = AlphaEnsemble.combine_signals(df, weights)

    # Expected: [0.6*1 + 0.4*0, 0.6*2 + 0.4*1, 0.6*3 + 0.4*2]
    # [0.6, 1.6, 2.6]
    expected = [0.6, 1.6, 2.6]
    assert list(ensemble) == pytest.approx(expected)


def test_edge_cases() -> None:
    """Verify empty inputs."""
    assert AlphaEnsemble.calculate_weights({}) == {}

    empty_df = pl.DataFrame()
    assert len(AlphaEnsemble.combine_signals(empty_df, {"a": 1.0})) == 0
