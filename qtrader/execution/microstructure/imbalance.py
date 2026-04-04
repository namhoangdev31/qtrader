from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class OrderbookImbalance:
    """
    Weighted Multi-Level Orderbook Imbalance Indicator.

    Quantifies buying vs. selling pressure by aggregating volumes
    across N levels with exponential depth decay:
    w_i = exp(-lambda * level)

    Output normalized to [-1, 1]:
    - +1: Strong buy pressure (bid-heavy)
    - -1: Strong sell pressure (ask-heavy)
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the imbalance model with calibrated decay parameters.
        """
        micro_cfg = config.microstructure.get("imbalance", {})
        self._n_levels = int(micro_cfg.get("n_levels", 5))
        self._lambda = float(micro_cfg.get("lambda_decay", 0.5))

        # Pre-compute weights for sub-1ms computation
        self._weights: np.ndarray[Any, np.dtype[np.float64]] = np.exp(
            -self._lambda * np.arange(self._n_levels)
        )

    def compute(self, bids: list[list[float]], asks: list[list[float]]) -> float:
        """
        Compute the weighted imbalance score for a given book snapshot.

        Args:
            bids: List of [price, size] at each level.
            asks: List of [price, size] at each level.
        """
        try:
            # 1. Truncate/Pad levels to match pre-computed weights
            bid_vols = self._extract_volumes(bids)
            ask_vols = self._extract_volumes(asks)

            # 2. Vectorized Weighted Aggregation
            weighted_bid_vol = np.dot(bid_vols, self._weights)
            weighted_ask_vol = np.dot(ask_vols, self._weights)

            total_vol = float(weighted_bid_vol + weighted_ask_vol)

            # 3. Normalization with Zero-Division Safety
            if total_vol <= 0:
                return 0.0

            return float((weighted_bid_vol - weighted_ask_vol) / total_vol)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            # High-performance silent failover for industrial-grade stability
            return 0.0

    def _extract_volumes(self, levels: list[list[float]]) -> np.ndarray[Any, np.dtype[np.float64]]:
        """Extract sizes up to N levels, padding with zeros if necessary."""
        # Pre-allocation for speed
        vols: np.ndarray[Any, np.dtype[np.float64]] = np.zeros(self._n_levels)
        actual_len = min(len(levels), self._n_levels)
        for i in range(actual_len):
            # Each level is [price, size]
            vols[i] = float(levels[i][1])
        return vols
