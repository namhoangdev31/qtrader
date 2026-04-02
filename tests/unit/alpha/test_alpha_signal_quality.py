"""
Level 2 Critical Tests: Alpha Signal Generation
Covers: MomentumAlpha, MeanReversionAlpha, TrendAlpha
Focus: output correctness, floating-point precision, look-ahead bias,
direction of signal, NaN propagation, and statelessness.
"""
import numpy as np
import polars as pl
import pytest

from qtrader.alpha.technical import MeanReversionAlpha, MomentumAlpha, TrendAlpha

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rising_prices(n=120, start=100.0, step=1.0):
    return pl.DataFrame({"close": [start + i * step for i in range(n)]})


def falling_prices(n=120, start=130.0, step=1.0):
    return pl.DataFrame({"close": [start - i * step for i in range(n)]})


def ohlcv(n=60, start=100.0):
    closes = [start + i * 0.5 for i in range(n)]
    return pl.DataFrame({
        "close": closes,
        "high":  [c + 0.5 for c in closes],
        "low":   [c - 0.5 for c in closes],
    })


# ---------------------------------------------------------------------------
# MomentumAlpha
# ---------------------------------------------------------------------------

class TestMomentumAlpha:
    def test_output_length_equals_input(self):
        df = rising_prices(50)
        alpha = MomentumAlpha(lookback=10, zscore_window=20)
        result = alpha.compute(df)
        assert result.len() == 50

    def test_output_name(self):
        result = MomentumAlpha(name="my_mom").compute(rising_prices(40))
        assert result.name == "my_mom"

    def test_rising_trend_positive_momentum(self):
        """Steady price rise → momentum signal should turn positive at the tail."""
        df = rising_prices(n=60)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        result = alpha.compute(df)
        tail = result.tail(10).drop_nulls()
        assert float(tail.mean()) > 0, "Expected positive momentum for rising prices"

    def test_falling_trend_negative_momentum(self):
        df = falling_prices(n=60)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        result = alpha.compute(df)
        tail = result.tail(10).drop_nulls()
        assert float(tail.mean()) < 0, "Expected negative momentum for falling prices"

    def test_look_ahead_bias_independence(self):
        """Value at index T must not change when future rows are appended."""
        df_short = rising_prices(n=40)
        df_long = rising_prices(n=60)  # adds 20 rows to the future
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        r_short = alpha.compute(df_short)
        r_long = alpha.compute(df_long)
        # Index 35 (interior) must be identical
        assert r_short[35] == pytest.approx(r_long[35], abs=1e-9), \
            "Look-ahead bias detected: future rows changed past value"

    def test_stateless_between_calls(self):
        df = rising_prices(50)
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        r1 = alpha.compute(df)
        r2 = alpha.compute(df)
        assert r1.equals(r2), "Alpha must be stateless between calls"

    def test_floating_point_tiny_changes(self):
        """Very tiny increments must not cause NaN due to near-zero variance."""
        prices = [100.0 + i * 1e-8 for i in range(50)]
        df = pl.DataFrame({"close": prices})
        alpha = MomentumAlpha(lookback=5, zscore_window=20)
        result = alpha.compute(df)
        # Should not be all NaN; at least the tail should have values
        assert not result.drop_nulls().is_empty()

    def test_non_negative_zscore_variance(self):
        """Z-score values should be finite with reasonable magnitude (not ±∞)."""
        df = rising_prices(60)
        result = MomentumAlpha(lookback=5, zscore_window=20).compute(df)
        finite = result.drop_nulls()
        assert finite.is_finite().all(), "Alpha values must be finite"

    def test_first_lookback_rows_are_null(self):
        """Before lookback periods, output should be null/NaN."""
        df = rising_prices(40)
        alpha = MomentumAlpha(lookback=10, zscore_window=20)
        result = alpha.compute(df)
        # The very first row must be null (insufficient data)
        assert result[0] is None or (result[0] is not None and np.isnan(result[0]))


# ---------------------------------------------------------------------------
# MeanReversionAlpha
# ---------------------------------------------------------------------------

class TestMeanReversionAlpha:
    def test_output_length(self):
        df = rising_prices(30)
        result = MeanReversionAlpha(lookback=3, zscore_window=10).compute(df)
        assert result.len() == 30

    def test_output_name(self):
        result = MeanReversionAlpha().compute(rising_prices(30))
        assert result.name == "mean_reversion"

    def test_spike_up_generates_negative_signal(self):
        """Price spikes above mean → expect to revert → signal should be negative."""
        prices = [100.0] * 20 + [150.0]   # sharp one-day spike
        df = pl.DataFrame({"close": prices})
        alpha = MeanReversionAlpha(lookback=5, zscore_window=10)
        result = alpha.compute(df)
        # Last value: price is well above rolling mean → raw = -(close - mean)/std < 0
        last = result.drop_nulls()[-1]
        assert float(last) < 0, "Spike up should produce negative mean-reversion signal"

    def test_spike_down_generates_positive_signal(self):
        prices = [100.0] * 20 + [50.0]
        df = pl.DataFrame({"close": prices})
        alpha = MeanReversionAlpha(lookback=5, zscore_window=10)
        result = alpha.compute(df)
        last = result.drop_nulls()[-1]
        assert float(last) > 0, "Spike down should produce positive mean-reversion signal"

    def test_look_ahead_bias_mean_reversion(self):
        """Mean reversion at index T must be identical with or without future data."""
        df_base = pl.DataFrame({"close": [100.0 + 5*np.sin(i/3) for i in range(30)]})
        df_ext = pl.concat([df_base, pl.DataFrame({"close": [200.0]*20})])
        alpha = MeanReversionAlpha(lookback=3, zscore_window=10)
        r_base = alpha.compute(df_base)
        r_ext = alpha.compute(df_ext)
        assert r_base[25] == pytest.approx(r_ext[25], abs=1e-9)

    def test_constant_prices_produce_nan_or_zero(self):
        """When all prices are identical, std=0. Division must not crash."""
        df = pl.DataFrame({"close": [100.0] * 20})
        alpha = MeanReversionAlpha(lookback=5, zscore_window=10)
        # Should not raise; resulting values may be NaN or 0
        result = alpha.compute(df)
        assert result is not None


# ---------------------------------------------------------------------------
# TrendAlpha
# ---------------------------------------------------------------------------

class TestTrendAlpha:
    def test_output_length(self):
        df = ohlcv(80)
        result = TrendAlpha(fast_window=5, slow_window=20, atr_window=5, zscore_window=30).compute(df)
        assert result.len() == 80

    def test_output_name(self):
        result = TrendAlpha(fast_window=2, slow_window=5, atr_window=3, zscore_window=5).compute(ohlcv(20))
        assert result.name == "trend"

    def test_persistent_uptrend_positive_signal(self):
        df = ohlcv(n=100, start=100.0)  # steadily rising
        alpha = TrendAlpha(fast_window=5, slow_window=20, atr_window=5, zscore_window=30)
        result = alpha.compute(df)
        tail = result.drop_nulls().tail(20)
        assert float(tail.mean()) > 0, "Uptrend should produce positive trend signal"

    def test_requires_high_low_columns(self):
        df_no_high = pl.DataFrame({"close": [100.0]*30, "low": [99.0]*30})
        alpha = TrendAlpha(fast_window=2, slow_window=5, atr_window=3, zscore_window=5)
        with pytest.raises(Exception):
            alpha.compute(df_no_high)
