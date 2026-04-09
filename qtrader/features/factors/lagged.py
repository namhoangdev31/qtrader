from __future__ import annotations
import polars as pl
from qtrader.features.base import BaseFeature

__all__ = ["AutoCorrelation", "LaggedReturn", "ReturnVolatility", "SkewFeature"]


class LaggedReturn(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, lag: int = 1, period: int = 1) -> None:
        self.lag = lag
        self.period = period
        self.name = f"lagged_ret_l{lag}_p{period}"
        self.min_periods = lag + period + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        raw_ret = (pl.col("close") / pl.col("close").shift(self.period)).log(base=2.718281828)
        lagged = raw_ret.shift(self.lag)
        return df.select(lagged.alias(self.name))[self.name]


class AutoCorrelation(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, window: int = 20, lag: int = 1) -> None:
        self.window = window
        self.lag = lag
        self.name = f"autocorr_w{window}_l{lag}"
        self.min_periods = window + lag + 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        ret = pl.col("close").pct_change()
        autocorr = ret.rolling_corr(ret.shift(self.lag), window_size=self.window)
        return df.select(autocorr.alias(self.name))[self.name]


class ReturnVolatility(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, window: int = 20, periods_per_year: int = 252) -> None:
        self.window = window
        self.periods_per_year = periods_per_year
        self.name = f"realized_vol_{window}"
        self.min_periods = window

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        log_ret = pl.col("close").log(base=2.718281828).diff()
        ann_vol = log_ret.rolling_std(self.window) * self.periods_per_year**0.5
        return df.select(ann_vol.alias(self.name))[self.name]


class SkewFeature(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close"]

    def __init__(self, window: int = 60) -> None:
        self.window = window
        self.name = f"return_skew_{window}"
        self.min_periods = window

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        log_ret = pl.col("close").log(base=2.718281828).diff()
        skew = log_ret.rolling_skew(self.window)
        return df.select(skew.alias(self.name))[self.name]
