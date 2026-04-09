import polars as pl
import pytest
from qtrader.alpha.ic import SignalAnalyzer

TEST_TOLERANCE = 1e-06
PERFECT_IC = 1.0
DECAY_MAX_LAG = 3
ROLLING_WINDOW = 3
EXPECTED_DATA_LEN = 7
CORR_THRESHOLD_LOW = 0.5
CORR_THRESHOLD_HIGH = 0.99
ZERO_IC = 0.0


@pytest.fixture
def sample_data() -> pl.DataFrame:
    return pl.DataFrame({"signal": [1.0, 2.0, 3.0, 2.0, 1.0], "return": [0.0, 1.0, 2.0, 3.0, 2.0]})


def test_compute_ic_perfect(sample_data: pl.DataFrame) -> None:
    ic = SignalAnalyzer.compute_ic(sample_data, "signal", "return", lag=1)
    assert abs(ic - PERFECT_IC) < TEST_TOLERANCE


def test_compute_ic_zero() -> None:
    df = pl.DataFrame({"signal": [1.0, 2.0, 3.0, 4.0, 5.0], "return": [5.0, 1.0, 4.0, 2.0, 3.0]})
    ic = SignalAnalyzer.compute_ic(df, "signal", "return", lag=1)
    assert abs(ic) < CORR_THRESHOLD_LOW


def test_ic_decay(sample_data: pl.DataFrame) -> None:
    decay = SignalAnalyzer.compute_ic_decay(sample_data, "signal", "return", max_lag=DECAY_MAX_LAG)
    assert decay[1] > CORR_THRESHOLD_HIGH
    assert decay[2] < CORR_THRESHOLD_LOW


def test_rolling_ic(sample_data: pl.DataFrame) -> None:
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
    assert abs(rolling_ic[2] - PERFECT_IC) < TEST_TOLERANCE
    assert abs(rolling_ic[5] - PERFECT_IC) < TEST_TOLERANCE


def test_edge_cases() -> None:
    empty_df = pl.DataFrame()
    assert SignalAnalyzer.compute_ic(empty_df, "s", "r") == ZERO_IC
    single_row = pl.DataFrame({"s": [1.0], "r": [1.0]})
    assert SignalAnalyzer.compute_ic(single_row, "s", "r") == ZERO_IC
