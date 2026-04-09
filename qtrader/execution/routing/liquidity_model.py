from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger("qtrader.execution.routing.liquidity_model")

class MultiVenueLiquidityModel:
    def __init__(self, n_levels: int = 5) -> None:
        self._n_levels = n_levels
        self._weights = [1.0 / (i + 1) for i in range(n_levels)]

    def compute_scores(
        self, market_data: dict[str, dict[str, Any]], side: str = "BUY"
    ) -> dict[str, float]:
        if not market_data:
            return {}
        raw_liquidity: dict[str, float] = {}
        total_l = 0.0
        for venue, orderbook in market_data.items():
            l_v = self._calculate_venue_liquidity(orderbook, side)
            raw_liquidity[venue] = l_v
            total_l += l_v
        scores: dict[str, float] = {}
        min_liquidity_threshold = 1e-12
        if total_l > min_liquidity_threshold:
            for venue, l_v in raw_liquidity.items():
                scores[venue] = l_v / total_l
        else:
            num_venues = len(market_data)
            uniform_score = 1.0 / num_venues
            scores = {venue: uniform_score for venue in market_data}
        return scores

    def _calculate_venue_liquidity(self, orderbook: dict[str, Any], side: str) -> float:
        try:
            key = "bids" if side.upper() == "SELL" else "asks"
            levels: list[list[float]] = orderbook.get(key, [])
            if not levels:
                return 0.0
            l_v = 0.0
            actual_levels = min(len(levels), self._n_levels)
            for i in range(actual_levels):
                min_fields = 2
                if len(levels[i]) < min_fields:
                    continue
                volume = float(levels[i][1])
                l_v += volume * self._weights[i]
            return l_v
        except Exception as e:
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("MultiVenueLiquidityModel: failed to compute venue liquidity", exc_info=True)
            return 0.0