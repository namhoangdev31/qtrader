from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger("qtrader.execution.routing.liquidity_model")


class MultiVenueLiquidityModel:
    """
    Multi-Venue Liquidity Model.

    Estimates available liquidity per venue by aggregating weighted orderbook depth.

    Mathematical Model:
    L_v = sum(w_i * V_{v,i})
    where:
    - V_{v,i}: Volume at level i of venue v
    - w_i: Weighting factor (1.0 / (level + 1)) prioritizing top-of-book depth.
    """

    def __init__(self, n_levels: int = 5) -> None:
        """
        Initialize the liquidity model with a fixed number of levels to track.

        Args:
            n_levels: Number of orderbook levels to aggregate (default: 5).
        """
        self._n_levels = n_levels
        # Pre-compute weights (Inverse level decay)
        self._weights = [1.0 / (i + 1) for i in range(n_levels)]

    def compute_scores(
        self, market_data: dict[str, dict[str, Any]], side: str = "BUY"
    ) -> dict[str, float]:
        """
        Compute normalized liquidity scores for all venues.

        Args:
            market_data: Dictionary mapping venue_name -> orderbook snapshot (bids/asks).
            side: Side to estimate liquidity for ('BUY' or 'SELL').

        Returns:
            Dictionary mapping venue_name -> normalized liquidity score in [0.0, 1.0].
            The sum of all scores will be 1.0 (relative ranking).
        """
        if not market_data:
            return {}

        raw_liquidity: dict[str, float] = {}
        total_l = 0.0

        for venue, orderbook in market_data.items():
            l_v = self._calculate_venue_liquidity(orderbook, side)
            raw_liquidity[venue] = l_v
            total_l += l_v

        # Normalization: Score_v = L_v / Total_L
        scores: dict[str, float] = {}
        min_liquidity_threshold = 1e-12
        if total_l > min_liquidity_threshold:
            for venue, l_v in raw_liquidity.items():
                scores[venue] = l_v / total_l
        else:
            # If no liquidity found across all venues, distribute uniformly as failsafe
            num_venues = len(market_data)
            uniform_score = 1.0 / num_venues
            scores = {venue: uniform_score for venue in market_data}

        return scores

    def _calculate_venue_liquidity(self, orderbook: dict[str, Any], side: str) -> float:
        """
        Compute weighted depth for a single venue snapshot.

        Args:
            orderbook: Orderbook snapshot with 'bids' or 'asks'.
            side: Side to check ('BUY' or 'SELL').
        """
        try:
            # Extract relevant levels based on side
            # "bids" for SELL (we sell into bids), "asks" for BUY (we buy into asks)
            key = "bids" if side.upper() == "SELL" else "asks"
            levels: list[list[float]] = orderbook.get(key, [])

            if not levels:
                return 0.0

            l_v = 0.0
            # Aggregate volume across the first N levels with decay weights
            actual_levels = min(len(levels), self._n_levels)
            for i in range(actual_levels):
                # Level format: [price, size, optional_metadata...]
                min_fields = 2
                if len(levels[i]) < min_fields:
                    continue
                volume = float(levels[i][1])
                l_v += volume * self._weights[i]

            return l_v

        except Exception:
            _LOG.error("MultiVenueLiquidityModel: failed to compute venue liquidity", exc_info=True)
            return 0.0
