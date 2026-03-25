import polars as pl
import pytest

from qtrader.hft.imbalance import OrderbookImbalance

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

L2_DATA = pl.DataFrame(
    {
        "bid_vol_0": [10.0, 50.0, 10.0, 50.0],
        "ask_vol_0": [10.0, 10.0, 100.0, 10.0],
    }
)

# 1. Raw Imbalance values:
# (10-10)/20 = 0.0
# (50-10)/60 = 0.666...
# (10-100)/110 = -0.818...


def test_imbalance_compute() -> None:
    """Verify L1 (top-level) orderbook imbalance computation with EMA."""
    processor = OrderbookImbalance()
    # Using span=1 (no smoothing) to verify raw logic
    span_1 = 1
    imbalance = processor.compute(L2_DATA, ema_span=span_1)

    expected_len = 4
    assert len(imbalance) == expected_len
    # (10-10)/(10+10) = 0.0
    val_0 = 0.0
    assert imbalance[0] == pytest.approx(val_0)
    # (50-10)/(50+10) = 40/60 = 0.666...
    val_1 = 0.666666666
    assert imbalance[1] == pytest.approx(val_1)
    # (10-100)/(10+100) = -90/110 = -0.8181818...
    val_2 = -0.818181818
    assert imbalance[2] == pytest.approx(val_2)


def test_imbalance_ema_smoothing() -> None:
    """Verify that EMA smoothing (span > 1) stabilizes the signal."""
    # Data has strong oscillations (0.0 -> 0.66 -> -0.81 -> 0.66)
    # Smooth signal should have dampened extremes
    span_10 = 10
    imbalance = OrderbookImbalance.compute(L2_DATA, ema_span=span_10)

    # First value should equal raw (EMA init)
    val_0 = 0.0
    assert imbalance[0] == pytest.approx(val_0)
    # Subsequent values should be dampened relative to raw 0.66
    extreme_val = 0.666666
    lower_bound = 0.0
    assert imbalance[1] < extreme_val
    assert imbalance[1] > lower_bound


def test_imbalance_multi_level() -> None:
    """Verify L2 depth-weighted imbalance computation."""
    l2_depth = pl.DataFrame(
        {
            "bid_vol_0": [10, 10],  # Imbalance 0.0
            "ask_vol_0": [10, 10],
            "bid_vol_1": [100, 10],  # Imbalance +0.81 at lvl 1
            "ask_vol_1": [10, 100],  # Imbalance -0.81 at lvl 1
        }
    )

    processor = OrderbookImbalance()
    # Span 1 to verify raw weighting
    span_1 = 1
    # Decay 0.5: Lvl 0 weight 1.0, Lvl 1 weight 0.5
    res = processor.compute_multi_level(l2_depth, levels=2, decay=0.5, ema_span=span_1)

    # (1.0*0.0 + 0.5*0.818181) / (1.5) = 0.409090 / 1.5 = 0.272727
    assert res[0] == pytest.approx(0.27272727)
    # (1.0*0.0 + 0.5*-0.818181) / (1.5) = -0.272727
    assert res[1] == pytest.approx(-0.27272727)


def test_imbalance_empty_robustness() -> None:
    """Verify robustness to empty DataFrames and division by zero."""
    empty = pl.DataFrame()
    res = OrderbookImbalance.compute(empty)
    assert len(res) == 0

    zero_vol = pl.DataFrame({"bid_vol_0": [0.0], "ask_vol_0": [0.0]})
    # Should not crash (epsilon protection)
    res_zero = OrderbookImbalance.compute(zero_vol)
    assert res_zero[0] == pytest.approx(0.0)
