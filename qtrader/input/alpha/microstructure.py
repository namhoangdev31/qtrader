from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from qtrader.input.alpha.base import Alpha, _zscore

__all__ = ["OrderImbalanceAlpha", "AmihudIlliquidityAlpha", "VPINAlpha"]


@dataclass(slots=True)
class OrderImbalanceAlpha:
    """Bid-ask volume imbalance as short-term directional signal."""

    window: int = 100
    name: str = "order_imbalance"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute z-scored order imbalance from L1 data."""
        if "bid_size" not in df.columns or "ask_size" not in df.columns:
            raise ValueError("OrderImbalanceAlpha requires 'bid_size' and 'ask_size' columns.")
        bid = df.get_column("bid_size")
        ask = df.get_column("ask_size")
        denom = bid + ask
        imbalance = (bid - ask) / denom
        imbalance = imbalance.to_frame("imb").with_columns(
            pl.when(pl.col("imb").is_finite()).then(pl.col("imb")).otherwise(0.0).alias("imb"),
        )["imb"]
        return _zscore(imbalance, self.window).rename(self.name)


@dataclass(slots=True)
class AmihudIlliquidityAlpha:
    """Amihud (2002) illiquidity proxy. High illiq → mean reversion signal."""

    window: int = 20
    name: str = "amihud"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Compute Amihud illiquidity and return its negative z-score."""
        close = df.get_column("close")
        volume = df.get_column("volume")
        ret = close.pct_change().abs()
        dollar_vol = close * volume
        illiq = ret / dollar_vol
        illiq = illiq.to_frame("x").with_columns(
            pl.when(pl.col("x").is_finite()).then(pl.col("x")).otherwise(0.0).alias("x"),
        )["x"]
        z = _zscore(illiq, self.window)
        return (-z).rename(self.name)


@dataclass(slots=True)
class VPINAlpha:
    """Flow toxicity proxy (VPIN-style). High toxicity → adverse selection risk."""

    window: int = 50
    name: str = "vpin"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        """Approximate VPIN using sign of price change to classify volume."""
        close = df.get_column("close")
        open_ = df.get_column("open")
        volume = df.get_column("volume")

        sign = pl.when(close > open_).then(1.0).otherwise(-1.0)
        buy_vol = volume * (sign > 0).cast(pl.Float64)
        sell_vol = volume * (sign < 0).cast(pl.Float64)

        buy_roll = buy_vol.rolling_sum(self.window)
        sell_roll = sell_vol.rolling_sum(self.window)
        tot_roll = volume.rolling_sum(self.window)
        vpin = (buy_roll - sell_roll).abs() / tot_roll
        vpin = vpin.to_frame("x").with_columns(
            pl.when(pl.col("x").is_finite()).then(pl.col("x")).otherwise(0.0).alias("x"),
        )["x"]
        z = _zscore(vpin, self.window)
        return (-z).rename(self.name)


"""
Pytest-style examples (conceptual):

def test_order_imbalance_requires_columns() -> None:
    df = pl.DataFrame({"close": [1.0]})
    alpha = OrderImbalanceAlpha()
    try:
        alpha.compute(df)
    except ValueError:
        assert True
"""

