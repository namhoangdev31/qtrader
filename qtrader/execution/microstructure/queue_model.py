from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class QueuePositionModel:
    def __init__(self, config: ExecutionConfig) -> None:
        micro_cfg = getattr(config, "microstructure", {}).get("queue_model", {})
        self._cancel_coeff = float(micro_cfg.get("cancellation_coeff", 0.5))
        self._default_intensity = float(micro_cfg.get("default_intensity", 10.0))
        self._volume_ahead: float = 0.0
        self._placed_timestamp: float = 0.0

    def place_order(self, volume_ahead: float, timestamp: float) -> None:
        self._volume_ahead = max(0.0, volume_ahead)
        self._placed_timestamp = timestamp

    def on_trade(self, trade_volume: float) -> float:
        self._volume_ahead = max(0.0, self._volume_ahead - trade_volume)
        return self._volume_ahead

    def on_cancellation(self, cancel_volume: float, total_level_volume: float) -> float:
        min_vol_epsilon = 1e-08
        if total_level_volume <= min_vol_epsilon:
            self._volume_ahead = 0.0
            return 0.0
        prob_ahead = float(self._volume_ahead / (total_level_volume + cancel_volume))
        depletion = cancel_volume * prob_ahead * self._cancel_coeff
        self._volume_ahead = max(0.0, self._volume_ahead - depletion)
        return self._volume_ahead

    def estimate_fill_prob(self, current_timestamp: float, intensity: float | None = None) -> float:
        min_vol_epsilon = 1e-08
        if self._volume_ahead <= min_vol_epsilon:
            return 1.0
        try:
            lam = intensity if intensity is not None else self._default_intensity
            delta_t = max(0.0, (current_timestamp - self._placed_timestamp) / 1000.0)
            exponent = -(lam * delta_t) / self._volume_ahead
            return float(1.0 - math.exp(exponent))
        except (ZeroDivisionError, OverflowError):
            return 1.0
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            return 0.0

    def reset(self) -> None:
        self._volume_ahead = 0.0
        self._placed_timestamp = 0.0
