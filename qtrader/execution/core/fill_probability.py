from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.core.fill_probability")


class FillProbabilityModel:
    """
    Fill Probability Estimation Model.

    Predicts the likelihood that a limit order will be executed given market conditions.

    Mathematical Model:
    P(fill) = 1 - exp(-lambda * t / Q_pos)

    Where:
    - lambda: trade intensity (execution rate of the level)
    - t: time horizon (seconds)
    - Q_pos: volume ahead in the orderbook queue
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the model with baseline intensity from configuration.
        """
        micro_cfg = getattr(config, "microstructure", {}).get("queue_model", {})
        self._default_intensity = float(micro_cfg.get("default_intensity", 10.0))

    def compute(
        self,
        intensity: float | None = None,
        time_horizon: float = 1.0,
        queue_pos: float | None = None,
    ) -> float:
        """
        Compute the calibrated fill probability.

        Args:
            intensity: Trade intensity (units/second). If None, uses default.
            time_horizon: Targeted time window for execution (seconds).
            queue_pos: Estimated volume ahead in the queue.

        Returns:
            Probability value in range [0.0, 1.0].
        """
        try:
            # 1. Logic Boundary: Zero queue means instant fill
            min_vol_epsilon = 1e-8
            q_pos = queue_pos if queue_pos is not None else 1.0
            if q_pos <= min_vol_epsilon:
                return 1.0

            # 2. Logic Boundary: No pressure or no time means no fill
            lam = intensity if intensity is not None else self._default_intensity
            if lam <= 0 or time_horizon <= 0:
                return 0.0

            # 3. Probability Calculation: P = 1 - exp(-lambda * t / Q)
            # This captures the Poisson execution process on the queue.
            exponent = -(lam * time_horizon) / q_pos
            prob = float(1.0 - math.exp(exponent))

            return max(0.0, min(1.0, prob))

        except (ZeroDivisionError, OverflowError):
            # Singularity implies high traffic relative to time/queue -> High fill prob
            return 1.0
        except Exception:
            # High-performance silent failover for industrial stability
            _LOG.error("FillProbabilityModel: computation failed", exc_info=True)
            return 0.0
