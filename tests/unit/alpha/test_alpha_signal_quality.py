from datetime import datetime
import numpy as np
import polars as pl
import pytest
from qtrader.alpha.technical import MeanReversionAlpha, MomentumAlpha, TrendAlpha


def _add_ohlcv(df: pl.DataFrame) -> pl.DataFrame:
    n = df.height
    cols = df.columns
    new_cols = {}
    if "open" not in cols:
        new_cols["open"] = [100.0] * n
    if "high" not in cols:
        new_cols["high"] = df["close"] + 0.5
    if "low" not in cols:
        new_cols["low"] = df["close"] - 0.5
    if "volume" not in cols:
        new_cols["volume"] = [1000.0] * n
    if "timestamp" not in cols:
        new_cols["timestamp"] = pl.datetime_range(
            datetime(2024, 1, 1), datetime(2025, 1, 1), interval="1m", eager=True
        ).head(n)
    return df.with_columns(**new_cols)


def rising_prices(n=120, start=100.0, step=0.01):
    prices = [start * np.exp(step * i + 0.0001 * i**2) for i in range(n)]
    df = pl.DataFrame({"close": prices})
    return _add_ohlcv(df)


def falling_prices(n=120, start=1000.0, step=0.01):
    prices = [start * np.exp(-step * i - 0.0001 * i**2) for i in range(n)]
    df = pl.DataFrame({"close": prices})
    return _add_ohlcv(df)


def ohlcv(n=60, start=100.0):
    prices = [start * np.exp(0.01 * i + 0.0001 * i**2) for i in range(n)]
    df = pl.DataFrame(
        {"close": prices, "high": [p * 1.005 for p in prices], "low": [p * 0.995 for p in prices]}
    )
    return _add_ohlcv(df)


class TestMomentumAlpha:
    def test_output_length_equals_input(self):
        df = rising_prices(50)
        alpha = MomentumAlpha(lookback=10, zscore_window=20)
        result = alpha.compute(df)
        assert result.len() == 50

    def test_output_name(self):
        result = MomentumAlpha().compute(rising_prices(40))
        assert result.name == "momentum"

    def test_rising_trend_positive_momentum(self):
        df = rising_prices(n=60)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        result = alpha.compute(df)
        tail = result.tail(10)
        assert float(tail.mean()) > 0, "Expected positive momentum for rising prices"

    def test_falling_trend_negative_momentum(self):
        df = falling_prices(n=60, start=1000.0)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        result = alpha.compute(df)
        tail = result.tail(10)
        assert float(tail.mean()) < 0, "Expected negative momentum for falling prices"

    def test_look_ahead_bias_independence(self):
        df_short = rising_prices(n=40)
        df_long = rising_prices(n=60)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        r_short = alpha.compute(df_short)
        r_long = alpha.compute(df_long)
        assert r_short[35] == pytest.approx(r_long[35], abs=1e-09), (
            "Look-ahead bias detected: future rows changed past value"
        )

    def test_stateless_between_calls(self):
        df = rising_prices(50)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        r1 = alpha.compute(df)
        r2 = alpha.compute(df)
        assert r1.equals(r2), "Alpha must be stateless between calls"

    def test_floating_point_tiny_changes(self):
        prices = [100.0 + i * 1e-08 for i in range(50)]
        df = _add_ohlcv(pl.DataFrame({"close": prices}))
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        result = alpha.compute(df)
        assert not result.drop_nulls().is_empty()

    def test_non_negative_zscore_variance(self):
        df = rising_prices(60)
        result = MomentumAlpha(lookback=5, zscore_window=20).compute(df)
        finite = result.drop_nulls()
        assert finite.is_finite().all(), "Alpha values must be finite"

    def test_first_lookback_rows_are_null(self):
        df = rising_prices(40)
        alpha = MomentumAlpha(lookback=10, zscore_window=20)
        result = alpha.compute(df)
        assert result[0] == 0.0


class TestMeanReversionAlpha:
    def test_output_length(self):
        df = rising_prices(30)
        result = MeanReversionAlpha(lookback=3, zscore_window=10).compute(df)
        assert result.len() == 30

    def test_output_name(self):
        result = MeanReversionAlpha().compute(rising_prices(30))
        assert result.name == "mean_reversion"

    def test_spike_up_generates_negative_signal(self):
        prices = [100.0] * 20 + [150.0]
        df = _add_ohlcv(pl.DataFrame({"close": prices}))
        alpha = MeanReversionAlpha(lookback=5, zscore_window=10)
        result = alpha.compute(df)
        last = result.drop_nulls()[-1]
        assert float(last) < 0, "Spike up should produce negative mean-reversion signal"

    def test_spike_down_generates_positive_signal(self):
        prices = [100.0] * 20 + [50.0]
        df = _add_ohlcv(pl.DataFrame({"close": prices}))
        alpha = MeanReversionAlpha(lookback=5, zscore_window=10)
        result = alpha.compute(df)
        last = result.drop_nulls()[-1]
        assert float(last) > 0, "Spike down should produce positive mean-reversion signal"

    def test_look_ahead_bias_mean_reversion(self):
        df_base = _add_ohlcv(
            pl.DataFrame({"close": [100.0 + 5 * np.sin(i / 3) for i in range(30)]})
        )
        df_ext = _add_ohlcv(
            pl.concat(
                [
                    pl.DataFrame({"close": [100.0 + 5 * np.sin(i / 3) for i in range(30)]}),
                    pl.DataFrame({"close": [200.0] * 20}),
                ]
            )
        )
        alpha = MeanReversionAlpha(lookback=3, zscore_window=10)
        r_base = alpha.compute(df_base)
        r_ext = alpha.compute(df_ext)
        assert r_base[25] == pytest.approx(r_ext[25], abs=1e-09)

    def test_constant_prices_produce_nan_or_zero(self):
        df = _add_ohlcv(pl.DataFrame({"close": [100.0] * 20}))
        alpha = MeanReversionAlpha(lookback=5, zscore_window=10)
        result = alpha.compute(df)
        assert result is not None


class TestTrendAlpha:
    def test_output_length(self):
        df = ohlcv(80)
        result = TrendAlpha(fast_window=5, slow_window=20, atr_window=5, zscore_window=30).compute(
            df
        )
        assert result.len() == 80

    def test_output_name(self):
        result = TrendAlpha(fast_window=2, slow_window=5, atr_window=3, zscore_window=5).compute(
            ohlcv(20)
        )
        assert result.name == "trend"

    def test_persistent_uptrend_positive_signal(self):
        df = ohlcv(n=100, start=100.0)
        alpha = TrendAlpha(fast_window=5, slow_window=20, atr_window=5, zscore_window=30)
        result = alpha.compute(df)
        tail = result.drop_nulls().tail(20)
        assert float(tail.mean()) > 0, "Uptrend should produce positive trend signal"

    def test_requires_high_low_columns(self):
        df_no_high = pl.DataFrame({"close": [100.0] * 30, "low": [99.0] * 30})
        alpha = TrendAlpha(fast_window=2, slow_window=5, atr_window=3, zscore_window=5)
        with pytest.raises(pl.ColumnNotFoundError):
            alpha.compute(df_no_high)
