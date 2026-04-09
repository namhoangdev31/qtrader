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
    def __init__(self, config: ExecutionConfig) -> None:
        self._config = config
        self._liquidity_model = MultiVenueLiquidityModel(n_levels=5)
        self._cost_model = RoutingCostModel(config)
        self._fill_model = VenueFillProbabilityModel(config)

    def route(
        self,
        order_size: float,
        side: str,
        market_data: dict[str, dict[str, Any]],
        latencies: dict[str, float],
        order_type: str = "MARKET",
        time_horizon: float = 1.0,
    ) -> dict[str, float]:
        if not market_data or order_size <= 0:
            return {}
        l_scores = self._liquidity_model.compute_scores(market_data, side)
        c_estimates = self._cost_model.estimate_costs(order_size, market_data, order_type, side)
        p_estimates = self._fill_model.estimate_fill_probabilities(
            time_horizon, market_data, latencies
        )
        venue_scores: dict[str, float] = {}
        total_s = 0.0
        for venue in market_data:
            p_v = p_estimates.get(venue, 0.0)
            l_v = l_scores.get(venue, 0.0)
            c_v = c_estimates.get(venue, 1.0)
            if c_v >= 1000000000000.0 or l_v <= 1e-12:
                s_v = 0.0
            else:
                s_v = p_v * l_v / max(1e-09, c_v)
            venue_scores[venue] = s_v
            total_s += s_v
        allocation: dict[str, float] = {}
        if total_s > 1e-12:
            for venue, s_v in venue_scores.items():
                split_qty = s_v / total_s * order_size
                if split_qty > 1e-08:
                    allocation[venue] = split_qty
        else:
            best_venue = (
                max(l_scores, key=lambda k: l_scores[k]) if l_scores else next(iter(market_data))
            )
            allocation[best_venue] = order_size
            _LOG.warning(
                "DynamicRoutingEngine: All scores zero. Defaulting to venue %s", best_venue
            )
        return allocation
