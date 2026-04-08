from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import polars as pl

from qtrader.alpha.base import BaseAlpha
from qtrader.features.microstructure_engine import MicrostructureFeatureEngine

__all__ = ["AmihudIlliquidityAlpha", "OrderImbalanceAlpha", "VPINAlpha", "MicropriceAlpha"]


@dataclass(slots=True)
class OrderImbalanceAlpha(BaseAlpha):
    """Bid-ask volume imbalance as short-term directional signal."""

    window: int = 100
    name: ClassVar[str] = "order_imbalance"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)
        self._engine = MicrostructureFeatureEngine(window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        """Compute raw order imbalance using high-performance engine."""
        if "bid_size" not in df.columns or "ask_size" not in df.columns:
            raise ValueError("OrderImbalanceAlpha requires 'bid_size' and 'ask_size' columns.")
        
        bid = df.get_column("bid_size").to_numpy()
        ask = df.get_column("ask_size").to_numpy()
        
        # Batch process using the engine
        results = [self._engine.get_imbalance(b, a) for b, a in zip(bid, ask, strict=False)]
        return pl.Series(name="imb", values=results, dtype=pl.Float64)


@dataclass(slots=True)
class AmihudIlliquidityAlpha(BaseAlpha):
    """Amihud (2002) illiquidity proxy. High illiq → mean reversion signal."""

    window: int = 20
    name: ClassVar[str] = "amihud"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        """Compute raw Amihud illiquidity."""
        close = df.get_column("close")
        volume = df.get_column("volume")
        ret = close.pct_change().abs()
        dollar_vol = close * volume
        illiq = ret / dollar_vol
        # Invert the signal: high illiq -> negative return expectation
        return -(illiq.to_frame("x").with_columns(
            pl.when(pl.col("x").is_finite()).then(pl.col("x")).otherwise(0.0).alias("x"),
        )["x"])


@dataclass(slots=True)
class VPINAlpha(BaseAlpha):
    """Flow toxicity proxy (VPIN-style). High toxicity → adverse selection risk."""

    window: int = 50
    name: ClassVar[str] = "vpin"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)
        self._engine = MicrostructureFeatureEngine(window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        """Approximate VPIN using high-performance Rust-backed engine."""
        volume = df.get_column("volume").to_numpy()
        close = df.get_column("close").to_numpy()
        open_ = df.get_column("open").to_numpy()
        
        results = []
        for i in range(len(volume)):
            side = "BUY" if close[i] > open_[i] else "SELL"
            vpin_val = self._engine.update_vpin(side, volume[i])
            results.append(vpin_val)
            
        return -pl.Series(name="vpin", values=results, dtype=pl.Float64)

@dataclass(slots=True)
class MicropriceAlpha(BaseAlpha):
    """Fair value estimator using LOB imbalance."""
    
    window: int = 20
    name: ClassVar[str] = "microprice"
    
    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)
        self._engine = MicrostructureFeatureEngine(window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        """Compute microprice from L1 book data."""
        bid_p = df.get_column("bid_price").to_numpy()
        ask_p = df.get_column("ask_price").to_numpy()
        bid_s = df.get_column("bid_size").to_numpy()
        ask_s = df.get_column("ask_size").to_numpy()
        
        results = [self._engine.get_microprice(bp, ap, bs, as_) for bp, ap, bs, as_ in zip(bid_p, ask_p, bid_s, ask_s, strict=False)]
        return pl.Series(name="microprice", values=results, dtype=pl.Float64)


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
