from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig

class OrderbookImbalance:
    def __init__(self, config: ExecutionConfig) -> None:
        micro_cfg = config.microstructure.get("imbalance", {})
        self._n_levels = int(micro_cfg.get("n_levels", 5))
        self._lambda = float(micro_cfg.get("lambda_decay", 0.5))
        self._weights: np.ndarray[Any, np.dtype[np.float64]] = np.exp(
            -self._lambda * np.arange(self._n_levels)
        )

    def compute(self, bids: list[list[float]], asks: list[list[float]]) -> float:
        try:
            bid_vols = self._extract_volumes(bids)
            ask_vols = self._extract_volumes(asks)
            weighted_bid_vol = np.dot(bid_vols, self._weights)
            weighted_ask_vol = np.dot(ask_vols, self._weights)
            total_vol = float(weighted_bid_vol + weighted_ask_vol)
            if total_vol <= 0:
                return 0.0
            return float((weighted_bid_vol - weighted_ask_vol) / total_vol)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            return 0.0

    def _extract_volumes(self, levels: list[list[float]]) -> np.ndarray[Any, np.dtype[np.float64]]:
        vols: np.ndarray[Any, np.dtype[np.float64]] = np.zeros(self._n_levels)
        actual_len = min(len(levels), self._n_levels)
        for i in range(actual_len):
            vols[i] = float(levels[i][1])
        return vols