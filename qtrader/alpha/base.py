from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class Alpha(Protocol):
    name: str

    def compute(self, df: pl.DataFrame) -> pl.Series:
        pass


class BaseAlpha(ABC):
    def __init__(self, name: str, standardize: bool = False, standardize_window: int = 100) -> None:
        self.name = name
        self.standardize = standardize
        self.standardize_window = standardize_window

    @abstractmethod
    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        pass

    def compute(self, df: pl.DataFrame) -> pl.Series:
        required = {"open", "high", "low", "close", "volume", "timestamp"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")
        try:
            raw = self._compute_raw(df)
        except Exception as e:
            import logging

            logging.getLogger(f"qtrader.alpha.{self.name}").error(
                f"Alpha {self.name} computation failed, returning neutral fallback: {e}"
            )
            return pl.Series(name=self.name, values=[0.0] * df.height, dtype=pl.Float64)
        if raw.len() != df.height:
            return pl.Series(name=self.name, values=[0.0] * df.height, dtype=pl.Float64)
        if raw.dtype != pl.Float64:
            raw = raw.cast(pl.Float64)
        if self.standardize:
            raw = _zscore(raw, self.standardize_window)
        raw = raw.fill_nan(0.0).fill_null(0.0)
        return raw.rename(self.name)


def _zscore(series: pl.Series, window: int) -> pl.Series:
    if window <= 1 or series.len() == 0:
        return pl.Series(name=series.name, values=[None] * series.len())
    df = pl.DataFrame({"x": series})
    roll = df.with_columns(
        pl.col("x").rolling_mean(window, min_samples=1).alias("m"),
        pl.col("x").rolling_std(window, min_samples=1).alias("s"),
    )
    z = (roll["x"] - roll["m"]) / (roll["s"] + 1e-12)
    return z.to_frame("z").with_columns(
        pl.when(roll["s"].is_not_null() & roll["s"].is_not_nan() & (roll["s"] > 1e-15))
        .then(pl.col("z"))
        .otherwise(None)
        .alias("z")
    )["z"]
