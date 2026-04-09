from __future__ import annotations

import numpy as np
import polars as pl

from qtrader.features.base import BaseFeature


class OrderImbalanceFactor(BaseFeature):
    """
    Polars-optimized implementation of Orderbook Imbalance.
    Expects columns: bid_vol_1, ask_vol_1, ..., bid_vol_N, ask_vol_N
    """
    name = "order_imbalance"
    version = "1.0"
    
    def __init__(self, n_levels: int = 5, lambda_decay: float = 0.5) -> None:
        self.n_levels = n_levels
        self.lambda_decay = lambda_decay
        self.required_cols = [f"bid_vol_{i}" for i in range(1, n_levels + 1)] + \
                             [f"ask_vol_{i}" for i in range(1, n_levels + 1)]
        self._weights = np.exp(-self.lambda_decay * np.arange(self.n_levels))

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        weighted_bid = pl.lit(0.0)
        weighted_ask = pl.lit(0.0)
        for i in range(self.n_levels):
            weighted_bid += pl.col(f"bid_vol_{i+1}") * self._weights[i]
            weighted_ask += pl.col(f"ask_vol_{i+1}") * self._weights[i]
            
        imbalance = (weighted_bid - weighted_ask) / (weighted_bid + weighted_ask + 1e-9)
        return df.select(imbalance.alias(self.name)).to_series()
