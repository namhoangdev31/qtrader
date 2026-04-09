from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import polars as pl

from qtrader.alpha.base import BaseAlpha

__all__ = ["MeanReversionAlpha", "MomentumAlpha", "TrendAlpha"]


@dataclass(slots=True)
class MomentumAlpha(BaseAlpha):
    lookback: int = 20
    zscore_window: int = 252
    name: ClassVar[str] = "momentum"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.zscore_window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        close = df.get_column("close")
        log_close = close.log()
        log_ret = log_close - log_close.shift(self.lookback)
        ret_std = log_ret.rolling_std(self.lookback)
        return log_ret / (ret_std + 1e-12)


@dataclass(slots=True)
class MeanReversionAlpha(BaseAlpha):
    lookback: int = 5
    zscore_window: int = 60
    name: ClassVar[str] = "mean_reversion"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.zscore_window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        close = df.get_column("close")
        mean = close.rolling_mean(self.lookback)
        std = close.rolling_std(self.lookback)
        return -(close - mean) / (std + 1e-12)


@dataclass(slots=True)
class TrendAlpha(BaseAlpha):
    fast_window: int = 10
    slow_window: int = 50
    atr_window: int = 14
    zscore_window: int = 100
    name: ClassVar[str] = "trend"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.zscore_window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
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
        return (sma_fast - sma_slow) / (atr + 1e-12)
