from __future__ import annotations

import polars as pl

from qtrader.features.base import BaseFeature

__all__ = ["OBV", "VWAP", "DollarVolume", "ForceIndex", "VolumeRatio"]


class OBV(BaseFeature):
    name: str = "obv"
    version: str = "1.0"
    required_cols: list[str] = ["close", "volume"]
    min_periods: int = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        direction = (
            pl.when(pl.col("close") > pl.col("close").shift(1))
            .then(1.0)
            .when(pl.col("close") < pl.col("close").shift(1))
            .then(-1.0)
            .otherwise(0.0)
        )
        signed_vol = (direction * pl.col("volume")).fill_null(0.0)
        return df.select(signed_vol.cum_sum().alias(self.name))[self.name]


class VWAP(BaseFeature):
    name: str = "vwap"
    version: str = "1.0"
    required_cols: list[str] = ["high", "low", "close", "volume"]
    min_periods: int = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        tp = (pl.col("high") + pl.col("low") + pl.col("close")) / 3.0
        tpv = tp * pl.col("volume")
        cum_tpv = tpv.cum_sum()
        cum_vol = pl.col("volume").cum_sum()
        vwap_expr = pl.when(cum_vol == 0.0).then(None).otherwise(cum_tpv / cum_vol)
        return df.select(vwap_expr.alias(self.name))[self.name]


class DollarVolume(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close", "volume"]
    min_periods: int = 1

    def __init__(self, rolling_window: int | None = None) -> None:
        self.rolling_window = rolling_window
        self.name = (
            "dollar_volume" if rolling_window is None else f"dollar_volume_{rolling_window}d"
        )

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        dv = pl.col("close") * pl.col("volume")
        if self.rolling_window is not None:
            dv = dv.rolling_sum(self.rolling_window)
        return df.select(dv.alias(self.name))[self.name]


class VolumeRatio(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["volume"]

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self.name = f"volume_ratio_{period}"
        self.min_periods = period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        avg_vol = pl.col("volume").rolling_mean(self.period)
        ratio = pl.when(avg_vol == 0.0).then(None).otherwise(pl.col("volume") / avg_vol)
        return df.select(ratio.alias(self.name))[self.name]


class ForceIndex(BaseFeature):
    version: str = "1.0"
    required_cols: list[str] = ["close", "volume"]

    def __init__(self, ema_period: int | None = 13) -> None:
        self.ema_period = ema_period
        self.name = "force_index" if ema_period is None else f"force_index_{ema_period}"
        self.min_periods = 1 if ema_period is None else ema_period

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        fi = pl.col("close").diff() * pl.col("volume")
        if self.ema_period is not None:
            fi = fi.ewm_mean(span=self.ema_period, adjust=False)
        return df.select(fi.fill_null(0.0).alias(self.name))[self.name]
