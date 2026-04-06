"""Volatility Indicators — ATR (Average True Range).

Provides the physical volatility baseline for the risk engine.
Fully vectorized using Polars expressions.
"""

from __future__ import annotations

from typing import ClassVar

import polars as pl

from qtrader.features.base import BaseFeature


class ATRFeature(BaseFeature):
    """Average True Range (ATR) indicator.

    Formula: 
      TR = max(H-L, abs(H-C_prev), abs(L-C_prev))
      ATR = EMA(TR, n)
    """

    name: ClassVar[str] = "atr"
    version: ClassVar[str] = "1.0"
    required_cols: ClassVar[list[str]] = ["high", "low", "close"]
    
    def __init__(self, window: int = 14) -> None:
        self.window = window
        self.min_periods = window

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute ATR using Polars expressions."""
        self.validate_inputs(df)
        
        # 1. Calculate True Range (TR)
        # Shift close for prev_close
        prev_close = pl.col("close").shift(1)
        
        tr_hl = pl.col("high") - pl.col("low")
        tr_hc = (pl.col("high") - prev_close).abs()
        tr_lc = (pl.col("low") - prev_close).abs()
        
        # Max of the three
        tr = pl.max_horizontal([tr_hl, tr_hc, tr_lc]).alias("tr")
        
        # 2. Calculate ATR (Simple EMA of TR)
        # We use ewm_mean for better performance in Polars
        # Note: min_periods was renamed to min_samples in Polars 1.21+
        atr_expr = tr.ewm_mean(span=self.window, min_samples=self.window).alias(self.name)
        
        return df.select(atr_expr).to_series()
