import polars as pl
import pytest

from qtrader.alpha.ic import SignalAnalyzer

# ──────────────────────────────────────────────
# Constants (PLR2004)
# ──────────────────────────────────────────────
TEST_TOLERANCE = 1e-6
PERFECT_IC = 1.0
DECAY_MAX_LAG = 3
ROLLING_WINDOW = 3
EXPECTED_DATA_LEN = 7
CORR_THRESHOLD_LOW = 0.5
CORR_THRESHOLD_HIGH = 0.99
ZERO_IC = 0.0


@pytest.fixture
def sample_data() -> pl.DataFrame:
    """Perfectly correlated signal with 1-lag return, but decays at lag 2."""
    # signal: [1, 2, 3, 2, 1]
    # return: [0, 1, 2, 3, 2]
    # Lag 1: [1, 2, 3, 2] vs [1, 2, 3, 2] -> IC=1.0
    # Lag 2: [1, 2, 3] vs [2, 3, 2] -> IC=0.0
    return pl.DataFrame({"signal": [1.0, 2.0, 3.0, 2.0, 1.0], "return": [0.0, 1.0, 2.0, 3.0, 2.0]})


def test_compute_ic_perfect(sample_data: pl.DataFrame) -> None:
    """Verify IC is 1.0 for perfectly correlated data."""
    ic = SignalAnalyzer.compute_ic(sample_data, "signal", "return", lag=1)
    assert abs(ic - PERFECT_IC) < TEST_TOLERANCE


def test_compute_ic_zero() -> None:
    """Verify IC is near 0 for uncorrelated data."""
    df = pl.DataFrame({"signal": [1.0, 2.0, 3.0, 4.0, 5.0], "return": [5.0, 1.0, 4.0, 2.0, 3.0]})
    ic = SignalAnalyzer.compute_ic(df, "signal", "return", lag=1)
    assert abs(ic) < CORR_THRESHOLD_LOW  # Uncorrelated data


def test_ic_decay(sample_data: pl.DataFrame) -> None:
    """Verify decay curve shows correct lag correlation."""
    decay = SignalAnalyzer.compute_ic_decay(sample_data, "signal", "return", max_lag=DECAY_MAX_LAG)

    assert decay[1] > CORR_THRESHOLD_HIGH  # Strong correlation at lag 1
    assert decay[2] < CORR_THRESHOLD_LOW  # Decay at lag 2


def test_rolling_ic(sample_data: pl.DataFrame) -> None:
    """Verify rolling IC matches point-in-time calculation."""
    # Add more data for rolling window 3
    df = pl.DataFrame(
        {
            "signal": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            "return": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        }
    )
    rolling_ic = SignalAnalyzer.compute_rolling_ic(
        df, "signal", "return", window=ROLLING_WINDOW, lag=1
    )

    assert len(rolling_ic) == EXPECTED_DATA_LEN
    # Last few values should be 1.0
    assert abs(rolling_ic[2] - PERFECT_IC) < TEST_TOLERANCE
    assert abs(rolling_ic[5] - PERFECT_IC) < TEST_TOLERANCE


def test_edge_cases() -> None:
    """Verify empty or insufficient data logic."""
    empty_df = pl.DataFrame()
    assert SignalAnalyzer.compute_ic(empty_df, "s", "r") == ZERO_IC

    single_row = pl.DataFrame({"s": [1.0], "r": [1.0]})
    assert SignalAnalyzer.compute_ic(single_row, "s", "r") == ZERO_IC
