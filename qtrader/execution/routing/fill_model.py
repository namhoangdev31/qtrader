from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qtrader.execution.core.fill_probability import FillProbabilityModel

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.routing.fill_model")


class VenueFillProbabilityModel:
    """
    Venue-Specific Fill Probability Model.

    Predicts the likelihood that a limit order will be executed at a specific venue,
    accounting for infrastructure latency and venue-specific trade dynamics.

    Mathematical Model:
    P(fill)_v = P(fill)_core(lambda_v, max(0, t - latency_v), Q_v)
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the venue fill model by composing the core probability engine.
        """
        self._core_model = FillProbabilityModel(config)

    def estimate_fill_probabilities(
        self,
        time_horizon: float,
        market_stats: dict[str, dict[str, Any]],
        latencies: dict[str, float],
    ) -> dict[str, float]:
        """
        Compute estimated fill probabilities for all candidate venues.

        Args:
            time_horizon: Targeted execution window (seconds).
            market_stats: Venue-specific microstructure (liquidity, intensity).
            latencies: Venue-specific round-trip latencies (seconds).

        Returns:
            Dictionary mapping venue_name -> fill probability in [0, 1].
        """
        if not market_stats:
            return {}

        if time_horizon <= 0:
            return {venue: 0.0 for venue in market_stats}

        probs: dict[str, float] = {}

        for venue, stats in market_stats.items():
            # 1. Retrieve venue-specific latency
            latency = latencies.get(venue, 0.0)

            # 2. Adjust time horizon: Execution window is reduced by network lag
            # If latency >= time_horizon, the fill probability is effectively zero.
            t_adj = max(0.0, time_horizon - latency)

            # 3. Pull venue-specific parameters
            # intensity (lambda) and liquidity (Q)
            # Default to None to allow core-model fallbacks
            intensity = stats.get("intensity")
            queue_pos = stats.get("liquidity")

            # 4. Compute core Poisson probability
            probs[venue] = self._core_model.compute(
                intensity=intensity, time_horizon=t_adj, queue_pos=queue_pos
            )

        return probs
