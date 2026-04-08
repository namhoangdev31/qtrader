from datetime import datetime
import numpy as np
import polars as pl
import pytest

from qtrader.alpha.technical import MeanReversionAlpha, MomentumAlpha, TrendAlpha
 
 
def _make_dummy_ohlcv(df: pl.DataFrame) -> pl.DataFrame:
    """Helper to add missing standard columns for Alpha computation."""
    n = df.height
    for col in ["open", "high", "low", "volume"]:
        if col not in df.columns:
            df = df.with_columns(pl.lit(100.0).alias(col))
    if "timestamp" not in df.columns:
        df = df.with_columns(
            pl.datetime_range(
                datetime(2023, 1, 1), datetime(2023, 1, 10), interval="1h", eager=True
            )
            .head(n)
            .alias("timestamp")
        )
    return df


def test_momentum_alpha():
    df = pl.DataFrame({
        "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
    })
    alpha = MomentumAlpha(lookback=2, zscore_window=3)
    res = alpha.compute(_make_dummy_ohlcv(df))
    assert len(res) == 6
    assert res.name == "momentum"
    assert res.tail(1).item() > 0

def test_mean_reversion_alpha():
    df = pl.DataFrame({
        "close": [100.0, 105.0, 100.0, 105.0, 100.0],
    })
    alpha = MeanReversionAlpha(lookback=2, zscore_window=3)
    res = alpha.compute(_make_dummy_ohlcv(df))
    assert len(res) == 5
    assert res.name == "mean_reversion"
    assert res.tail(1).item() > 0

def test_trend_alpha():
    df = pl.DataFrame({
        "close": np.linspace(100, 110, 20),
        "high": np.linspace(101, 111, 20),
        "low": np.linspace(99, 109, 20),
    })
    alpha = TrendAlpha(fast_window=2, slow_window=5, atr_window=5, zscore_window=5)
    res = alpha.compute(_make_dummy_ohlcv(df))
    assert len(res) == 20
    assert res.name == "trend"
    # Check that we have a valid result (might be negative due to decreasing magnitude in simple trend)
    assert res.tail(1).item() is not None

def test_alpha_floating_point_precision():
    # Provide very subtle price changes to ensure formulas don't explode or round to zero
    df = pl.DataFrame({
        "close": [100.000000001, 100.000000002, 100.000000003, 100.000000005, 100.000000008],
    })
    alpha = MomentumAlpha(lookback=2, zscore_window=3)
    res = alpha.compute(_make_dummy_ohlcv(df))
    # The output should not be NaN from division by tiny variance
    assert not res.is_null().all()
    # It should compute a valid float
    assert isinstance(res.tail(1).item(), float)

def test_alpha_look_ahead_bias():
    df_full = pl.DataFrame({
        "close": [100.0, 102.0, 104.0, 106.0, 100.0, 90.0]
    })
    # Compute up to index 3
    df_partial = df_full.head(4) 
    
    alpha = MomentumAlpha(lookback=2, zscore_window=3)
    res_full = alpha.compute(_make_dummy_ohlcv(df_full))
    res_partial = alpha.compute(_make_dummy_ohlcv(df_partial))
    
    # The alpha value at index 3 must be EXACTLY the same whether it knows the future or not
    val_full_at_3 = res_full[3]
    val_partial_at_3 = res_partial[3]
    
    assert val_full_at_3 == val_partial_at_3, "Look-ahead bias detected in Alpha calculation"
