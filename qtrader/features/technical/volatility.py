from __future__ import annotations
from typing import ClassVar
import polars as pl
from qtrader.features.base import BaseFeature


class ATRFeature(BaseFeature):
    name: ClassVar[str] = "atr"
    version: ClassVar[str] = "1.0"
    required_cols: ClassVar[list[str]] = ["high", "low", "close"]

    def __init__(self, window: int = 14) -> None:
        self.window = window
        self.min_periods = window

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        prev_close = pl.col("close").shift(1)
        tr_hl = pl.col("high") - pl.col("low")
        tr_hc = (pl.col("high") - prev_close).abs()
        tr_lc = (pl.col("low") - prev_close).abs()
        tr = pl.max_horizontal([tr_hl, tr_hc, tr_lc]).alias("tr")
        atr_expr = tr.ewm_mean(span=self.window, min_samples=self.window).alias(self.name)
        return df.select(atr_expr).to_series()
