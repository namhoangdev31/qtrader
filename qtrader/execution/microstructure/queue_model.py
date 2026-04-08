from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class QueuePositionModel:
    """
    Limit Order Queue Position and Fill Probability Model.

    Tracks the 'Virtual Queue' ahead of a rested order by correlating
    trades (direct depletion) and cancellations (stochastic depletion).

    Mathematical Model:
    P(fill) = 1 - exp(-lambda * t / Q)
    where:
    - Q: Volume ahead in queue
    - lambda: Execution intensity (trades per second)
    - t: Elapsed time
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the queue model with forensic cancellation coefficients.
        """
        micro_cfg = getattr(config, "microstructure", {}).get("queue_model", {})
        self._cancel_coeff = float(micro_cfg.get("cancellation_coeff", 0.5))
        self._default_intensity = float(micro_cfg.get("default_intensity", 10.0))

        # State for a single tracked order
        self._volume_ahead: float = 0.0
        self._placed_timestamp: float = 0.0

    def place_order(self, volume_ahead: float, timestamp: float) -> None:
        """
        Mark the placement of a limit order and initialize its queue position.

        Args:
            volume_ahead: Total volume ahead of the order at the price level.
            timestamp: Unix timestamp (ms) of placement.
        """
        self._volume_ahead = max(0.0, volume_ahead)
        self._placed_timestamp = timestamp

    def on_trade(self, trade_volume: float) -> float:
        """
        Update queue position following a trade at the same price level.

        Args:
            trade_volume: Total volume executed in the trade event.
        """
        # Trades deplete the queue from the front
        self._volume_ahead = max(0.0, self._volume_ahead - trade_volume)
        return self._volume_ahead

    def on_cancellation(self, cancel_volume: float, total_level_volume: float) -> float:
        """
        Update queue position following a cancellation at the same price level.

        Args:
            cancel_volume: Volume of order(s) cancelled.
            total_level_volume: Total remaining volume at the price level.
        """
        min_vol_epsilon = 1e-8
        if total_level_volume <= min_vol_epsilon:
            self._volume_ahead = 0.0
            return 0.0

        # Stochastic cancellation: Assume portion of cancels are ahead of us
        # based on our relative position in the book.
        # Ratio Q/Total represents our "unluckiness" probability.
        prob_ahead = float(self._volume_ahead / (total_level_volume + cancel_volume))
        depletion = cancel_volume * prob_ahead * self._cancel_coeff

        self._volume_ahead = max(0.0, self._volume_ahead - depletion)
        return self._volume_ahead

    def estimate_fill_prob(self, current_timestamp: float, intensity: float | None = None) -> float:
        """
        Estimate the probability [0, 1] that the order will be filled.

        Args:
            current_timestamp: Current Unix timestamp (ms).
            intensity: Optional trade intensity override (trades/sec).
        """
        min_vol_epsilon = 1e-8
        if self._volume_ahead <= min_vol_epsilon:
            return 1.0

        try:
            lam = intensity if intensity is not None else self._default_intensity
            # Delta T in seconds
            delta_t = max(0.0, (current_timestamp - self._placed_timestamp) / 1000.0)

            # 1 - exp(-lambda * t / Q)
            # Higher lambda, higher t, or lower Q all increase fill probability.
            exponent = -(lam * delta_t) / self._volume_ahead
            return float(1.0 - math.exp(exponent))
        except (ZeroDivisionError, OverflowError):
            return 1.0
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            # High-performance silent failover for industrial-grade stability
            return 0.0

    def reset(self) -> None:
        """Reset the internal queue tracker state."""
        self._volume_ahead = 0.0
        self._placed_timestamp = 0.0
