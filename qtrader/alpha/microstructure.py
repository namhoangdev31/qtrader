from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
import polars as pl
from qtrader.alpha.base import BaseAlpha
from qtrader.features.microstructure_engine import MicrostructureFeatureEngine

__all__ = ["AmihudIlliquidityAlpha", "MicropriceAlpha", "OrderImbalanceAlpha", "VPINAlpha"]


@dataclass(slots=True)
class OrderImbalanceAlpha(BaseAlpha):
    window: int = 100
    name: ClassVar[str] = "order_imbalance"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)
        self._engine = MicrostructureFeatureEngine(window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        if "bid_size" not in df.columns or "ask_size" not in df.columns:
            raise ValueError("OrderImbalanceAlpha requires 'bid_size' and 'ask_size' columns.")
        bid = df.get_column("bid_size").to_numpy()
        ask = df.get_column("ask_size").to_numpy()
        results = [self._engine.get_imbalance(b, a) for (b, a) in zip(bid, ask, strict=False)]
        return pl.Series(name="imb", values=results, dtype=pl.Float64)


@dataclass(slots=True)
class AmihudIlliquidityAlpha(BaseAlpha):
    window: int = 20
    name: ClassVar[str] = "amihud"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        close = df.get_column("close")
        volume = df.get_column("volume")
        ret = close.pct_change().abs()
        dollar_vol = close * volume
        illiq = ret / dollar_vol
        return -illiq.to_frame("x").with_columns(
            pl.when(pl.col("x").is_finite()).then(pl.col("x")).otherwise(0.0).alias("x")
        )["x"]


@dataclass(slots=True)
class VPINAlpha(BaseAlpha):
    window: int = 50
    name: ClassVar[str] = "vpin"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)
        self._engine = MicrostructureFeatureEngine(window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
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
    window: int = 20
    name: ClassVar[str] = "microprice"

    def __post_init__(self) -> None:
        super().__init__(name=self.name, standardize=True, standardize_window=self.window)
        self._engine = MicrostructureFeatureEngine(window=self.window)

    def _compute_raw(self, df: pl.DataFrame) -> pl.Series:
        bid_p = df.get_column("bid_price").to_numpy()
        ask_p = df.get_column("ask_price").to_numpy()
        bid_s = df.get_column("bid_size").to_numpy()
        ask_s = df.get_column("ask_size").to_numpy()
        results = [
            self._engine.get_microprice(bp, ap, bs, as_)
            for (bp, ap, bs, as_) in zip(bid_p, ask_p, bid_s, ask_s, strict=False)
        ]
        return pl.Series(name="microprice", values=results, dtype=pl.Float64)
