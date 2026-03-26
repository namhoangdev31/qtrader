from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["MeanReversionAlpha", "MomentumAlpha", "TrendAlpha"]


@dataclass(slots=True)
class MomentumAlpha:
    """Price momentum with volatility adjustment."""

    lookback: int = 20
    zscore_window: int = 252
    name: str = "momentum"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute volatility-adjusted momentum and z-score it."""
        close = df.get_column("close")
        log_close = close.log()
        log_ret = log_close - log_close.shift(self.lookback)
        ret_std = log_ret.rolling_std(self.lookback)
        log_ret / (ret_std + 1e-12)
        
        signal = log_ret / (ret_std + 1e-12)
        return signal.rename(self.name)


@dataclass(slots=True)
class MeanReversionAlpha:
    """Short-term price reversal."""

    lookback: int = 5
    zscore_window: int = 60
    name: str = "mean_reversion"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute mean reversion signal from recent price deviations."""
        close = df.get_column("close")
        mean = close.rolling_mean(self.lookback)
        std = close.rolling_std(self.lookback)
        signal = -(close - mean) / (std + 1e-12)
        return signal.fill_nan(0.0).fill_null(0.0).rename(self.name)


@dataclass(slots=True)
class TrendAlpha:
    """Moving average crossover with ATR filter."""

    fast_window: int = 10
    slow_window: int = 50
    atr_window: int = 14
    zscore_window: int = 100
    name: str = "trend"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute trend-following alpha using SMA crossover and ATR."""
        close = df.get_column("close")
        high = df.get_column("high")
        low = df.get_column("low")

        sma_fast = close.rolling_mean(self.fast_window)
        sma_slow = close.rolling_mean(self.slow_window)

        prev_close = close.shift(1)
        tr1 = (high - low).abs()
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pl.select(pl.max_horizontal(tr1, tr2, tr3)).to_series()
        atr = true_range.rolling_mean(self.atr_window)

        signal = (sma_fast - sma_slow) / (atr + 1e-12)
        return signal.rename(self.name)


"""
Pytest-style examples (conceptual):

def test_momentum_alpha_length() -> None:
    df = pl.DataFrame({"close": [1.0, 1.1, 1.2, 1.3, 1.4]})
    alpha = MomentumAlpha(lookback=1, zscore_window=3)
    out = alpha.compute(df)
    assert out.len() == df.height


def test_mean_reversion_alpha_name() -> None:
    df = pl.DataFrame({"close": [1.0, 0.9, 1.1, 0.95, 1.05]})
    alpha = MeanReversionAlpha()
    out = alpha.compute(df)
    assert out.name == "mean_reversion"
"""

