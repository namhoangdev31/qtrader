import numpy as np
import polars as pl
import pytest

from qtrader.alpha.decay import AlphaDecayDetector


@pytest.fixture
def decaying_ic() -> pl.Series:
    """Generate a decaying IC series."""
    # [0.05, 0.04, 0.03, 0.02, 0.01, 0.00, -0.01]
    return pl.Series("ic", [0.05, 0.04, 0.03, 0.02, 0.01, 0.0, -0.01])


def test_is_decaying_stable() -> None:
    """Verify that stable high IC does not trigger decay."""
    stable_ic = pl.Series("ic", [0.05, 0.05, 0.05])
    assert not AlphaDecayDetector.is_decaying(stable_ic, threshold=0.01)


def test_is_decaying_trigger(decaying_ic: pl.Series) -> None:
    """Verify that falling IC triggers decay."""
    # Latest value is -0.01 < 0.01
    assert AlphaDecayDetector.is_decaying(decaying_ic, threshold=0.01)

    # Check with higher threshold
    assert AlphaDecayDetector.is_decaying(decaying_ic, threshold=0.06)


def test_check_signal_health_basic() -> None:
    """Verify full pipeline with synthetic data."""
    # Perfectly correlated at start, then uncorrelated
    np.random.seed(42)
    n = 1000
    signal = np.random.normal(0, 1, n)
    returns = np.zeros(n)

    # First half: high correlation (0.9)
    returns[1:500] = 0.9 * signal[:499]
    # Second half: noise
    returns[500:] = np.random.normal(0, 1, 500)

    df = pl.DataFrame({"signal": signal, "return": returns})

    # Check health with window of 100
    is_dead = AlphaDecayDetector.check_signal_health(
        df, "signal", "return", monitoring_params={"window": 100, "threshold": 0.05}
    )

    # At the end of the series (second half), it should be decaying
    assert is_dead


def test_edge_cases() -> None:
    """Verify empty and null logic."""
    assert not AlphaDecayDetector.is_decaying(pl.Series())

    null_ic = pl.Series("ic", [None])
    assert not AlphaDecayDetector.is_decaying(null_ic)

    empty_df = pl.DataFrame()
    assert AlphaDecayDetector.check_signal_health(empty_df, "s", "r")
