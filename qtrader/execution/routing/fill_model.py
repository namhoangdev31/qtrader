from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from qtrader.execution.core.fill_probability import FillProbabilityModel

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig
_LOG = logging.getLogger("qtrader.execution.routing.fill_model")


class VenueFillProbabilityModel:
    def __init__(self, config: ExecutionConfig) -> None:
        self._core_model = FillProbabilityModel(config)

    def estimate_fill_probabilities(
        self,
        time_horizon: float,
        market_stats: dict[str, dict[str, Any]],
        latencies: dict[str, float],
    ) -> dict[str, float]:
        if not market_stats:
            return {}
        if time_horizon <= 0:
            return {venue: 0.0 for venue in market_stats}
        probs: dict[str, float] = {}
        for venue, stats in market_stats.items():
            latency = latencies.get(venue, 0.0)
            t_adj = max(0.0, time_horizon - latency)
            intensity = stats.get("intensity")
            queue_pos = stats.get("liquidity")
            probs[venue] = self._core_model.compute(
                intensity=intensity, time_horizon=t_adj, queue_pos=queue_pos
            )
        return probs
