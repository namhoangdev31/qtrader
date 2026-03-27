from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qtrader.execution.routing.cost_model import RoutingCostModel
from qtrader.execution.routing.fill_model import VenueFillProbabilityModel
from qtrader.execution.routing.liquidity_model import MultiVenueLiquidityModel

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.routing.router")


class DynamicRoutingEngine:
    """
    Dynamic Smart Order Routing (SOR) Engine.

    The central orchestrator for cross-venue routing decisions. Integrates Liquidity,
    Cost, and Fill Probability models to determine the optimal execution path.

    Scoring Function:
    Score_v = (P_fill,v * L_v) / C_v
    where:
    - P_v: Venue fill probability (latency-adjusted execution likelihood)
    - L_v: Venue liquidity score (weighted top-of-book depth)
    - C_v: Venue execution cost (Spread + Fees + Slippage)
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the routing engine with constituent sub-models.
        """
        self._config = config
        self._liquidity_model = MultiVenueLiquidityModel(n_levels=5)
        self._cost_model = RoutingCostModel(config)
        self._fill_model = VenueFillProbabilityModel(config)

    def route(self, order_size: float, side: str, market_data: dict[str, dict[str, Any]], latencies: dict[str, float], order_type: str = "MARKET", time_horizon: float = 1.0) -> dict[str, float]:  # noqa: PLR0913, E501
        """
        Generate optimal order allocation across candidate venues.

        Args:
            order_size: Total targeted order quantity.
            side: 'BUY' or 'SELL'.
            market_data: Venue orderbook snapshots and microstructure stats.
            latencies: Venue-specific round-trip latencies (seconds).
            order_type: 'MARKET' or 'LIMIT'.
            time_horizon: Intended execution window (seconds).

        Returns:
            Dictionary mapping venue_name -> allocated portion of order_size.
        """
        if not market_data or order_size <= 0:
            return {}

        # 1. Evaluate Venues: Extract component signals
        # L_v: Relative liquidity ranking
        l_scores = self._liquidity_model.compute_scores(market_data, side)

        # C_v: Holistic absolute cost estimation
        c_estimates = self._cost_model.estimate_costs(order_size, market_data, order_type, side)

        # P_v: Latency-adjusted fill probability
        p_estimates = self._fill_model.estimate_fill_probabilities(
            time_horizon, market_data, latencies
        )

        # 2. Score Venues: S_v = (P_v * L_v) / C_v
        venue_scores: dict[str, float] = {}
        total_s = 0.0

        for venue in market_data:
            p_v = p_estimates.get(venue, 0.0)
            l_v = l_scores.get(venue, 0.0)
            c_v = c_estimates.get(venue, 1.0)  # Cost model includes failsafe-high cost

            # Filter out infinite cost or zero liquidity venues
            # failsafe_high = 1e18
            if c_v >= 1e12 or l_v <= 1e-12:  # noqa: PLR2004
                s_v = 0.0
            else:
                # Maximize success likelihood and depth, minimize cost
                s_v = (p_v * l_v) / max(1e-9, c_v)

            venue_scores[venue] = s_v
            total_s += s_v

        # 3. Select / Split: Prorate order_size based on normalized scores
        allocation: dict[str, float] = {}
        if total_s > 1e-12:  # noqa: PLR2004
            for venue, s_v in venue_scores.items():
                # Prorated split across best performing venues
                split_qty = (s_v / total_s) * order_size
                if split_qty > 1e-8:  # noqa: PLR2004
                    allocation[venue] = split_qty
        else:
            # Failsafe: Fallback to best known liquidity venue
            best_venue = (
                max(l_scores, key=lambda k: l_scores[k])
                if l_scores
                else next(iter(market_data))
            )
            allocation[best_venue] = order_size

            _LOG.warning(
                "DynamicRoutingEngine: All scores zero. Defaulting to venue %s", best_venue
            )

        return allocation
