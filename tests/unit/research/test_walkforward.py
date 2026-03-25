import polars as pl

from qtrader.research.walkforward import WalkforwardEngine

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
TOTAL_ROWS = 100
TRAIN_SIZE = 60
TEST_SIZE = 20
STEP_SIZE = 20
EXPECTED_WINDOWS_BASIC = 2
INDEX_0 = 0
INDEX_1 = 1
VAL_0 = 0
VAL_20 = 20
VAL_40 = 40
VAL_60 = 60
VAL_80 = 80
VAL_100 = 100
VAL_30 = 30
VAL_50 = 50
VAL_99 = 99
VAL_10 = 10
VAL_2 = 2


def test_generate_windows_basic() -> None:
    """Verify window generation logic."""
    windows = list(
        WalkforwardEngine.generate_windows(TOTAL_ROWS, TRAIN_SIZE, TEST_SIZE, step=STEP_SIZE)
    )
    assert len(windows) == EXPECTED_WINDOWS_BASIC

    # 1st window
    assert windows[INDEX_0][0].start == VAL_0
    assert windows[INDEX_0][0].stop == VAL_60
    assert windows[INDEX_0][1].start == VAL_60
    assert windows[INDEX_0][1].stop == VAL_80

    # 2nd window
    assert windows[INDEX_1][0].start == VAL_20
    assert windows[INDEX_1][0].stop == VAL_80
    assert windows[INDEX_1][1].start == VAL_80
    assert windows[INDEX_1][1].stop == VAL_100


def test_generate_windows_no_overlap() -> None:
    """Verify non-overlapping OOS windows (default step)."""
    windows = list(WalkforwardEngine.generate_windows(TOTAL_ROWS, VAL_40, VAL_30))
    assert len(windows) == VAL_2
    assert windows[INDEX_1][1].stop == VAL_100


def test_generate_windows_insufficient_data() -> None:
    """Verify handling of small datasets."""
    windows = list(WalkforwardEngine.generate_windows(VAL_50, VAL_40, VAL_20))
    zero_len = 0
    assert len(windows) == zero_len


def test_run_validation_mock() -> None:
    """Verify aggregation using a mock model."""
    df = pl.DataFrame({"val": range(TOTAL_ROWS)})

    def mock_model(train: pl.DataFrame, test: pl.DataFrame) -> pl.DataFrame:
        # Just return the OOS test data with a mean flag
        return test.with_columns(pl.lit(train["val"].mean()).alias("train_mean"))

    results = WalkforwardEngine.run_validation(
        df, mock_model, train_size=TRAIN_SIZE, test_size=TEST_SIZE, step=STEP_SIZE
    )

    # Expected: 2 windows (60-80, 80-100) -> 40 rows
    assert results.height == VAL_40
    assert "train_mean" in results.columns

    # Check distinct OOS segments
    oos_vals = results["val"].to_list()
    assert oos_vals[INDEX_0] == VAL_60
    assert oos_vals[-1] == VAL_99


def test_run_validation_empty() -> None:
    """Verify return empty DF for no windows."""
    df = pl.DataFrame({"a": [1, 2]})
    results = WalkforwardEngine.run_validation(df, lambda tr, te: tr, VAL_10, VAL_10)
    assert results.is_empty()
