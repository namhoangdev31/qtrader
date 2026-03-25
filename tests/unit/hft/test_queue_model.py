import polars as pl
import pytest

from qtrader.hft.queue_model import QueueModel

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

TEST_DATA = pl.DataFrame(
    {
        "bid_vol_0": [100.0, 100.0, 50.0, 0.0],
        "exec_rate_rolling": [10.0, 100.0, 100.0, 10.0],
    }
)

# Configuration for unit tests
HORIZON = 5.0


def test_queue_model_fill_probability() -> None:
    """Verify fill probability calculation with different queue dynamics."""
    model = QueueModel()
    probs = model.estimate_fill_probability(
        TEST_DATA,
        queue_depth_col="bid_vol_0",
        exec_rate_col="exec_rate_rolling",
        horizon_seconds=HORIZON,
    )

    expected_len = 4
    assert len(probs) == expected_len

    # 1. Rate 10, Horizon 5, Queue 100 -> Expected 50/100 = 0.5
    val_0 = 0.5
    assert probs[0] == pytest.approx(val_0)

    # 2. Rate 100, Horizon 5, Queue 100 -> Expected 1.0 (clamped)
    val_1 = 1.0
    assert probs[1] == pytest.approx(val_1)

    # 3. Rate 100, Horizon 5, Queue 50  -> Expected 1.0 (clamped)
    val_2 = 1.0
    assert probs[2] == pytest.approx(val_2)

    # 4. Zero Queue -> Expected 1.0 (automatic fill)
    val_3 = 1.0
    assert probs[3] == pytest.approx(val_3)


def test_queue_model_wait_time() -> None:
    """Verify estimated wait time for full execution."""
    model = QueueModel()

    # Queue 100, Rate 10 -> Wait 10s
    wait = model.estimate_wait_time(100.0, 10.0)
    assert wait == pytest.approx(10.0)

    # Queue 50, Rate 100 -> Wait 0.5s
    wait_fast = model.estimate_wait_time(50.0, 100.0)
    assert wait_fast == pytest.approx(0.5)


def test_queue_model_empty_robustness() -> None:
    """Ensure robustness to empty DataFrames."""
    model = QueueModel()
    empty = pl.DataFrame()
    res = model.estimate_fill_probability(empty)
    assert len(res) == 0
