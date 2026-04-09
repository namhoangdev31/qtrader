from __future__ import annotations
import statistics
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class SpreadDynamicsModel:
    def __init__(self, config: ExecutionConfig) -> None:
        micro_cfg = getattr(config, "microstructure", {}).get("spread_model", {})
        self._window_size = int(micro_cfg.get("window_size", 20))
        self._alpha = float(micro_cfg.get("alpha", 0.1))
        self._beta = float(micro_cfg.get("beta", 0.05))
        self._mid_prices: deque[float] = deque(maxlen=self._window_size)
        self._spreads: deque[float] = deque(maxlen=self._window_size)

    def update(self, bid: float, ask: float, volume: float) -> float:
        try:
            current_spread = ask - bid
            mid_price = (ask + bid) / 2.0
            self._mid_prices.append(mid_price)
            self._spreads.append(current_spread)
            local_vol = self._compute_vol()
            local_liq = volume
            predicted = current_spread + self._alpha * local_vol - self._beta * local_liq
            min_samples = 5
            if len(self._mid_prices) < min_samples:
                return current_spread
            min_spread = 1e-08
            return max(min_spread, predicted)
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            if self._spreads:
                return float(sum(self._spreads) / len(self._spreads))
            return 0.0

    def _compute_vol(self) -> float:
        min_vol_samples = 2
        if len(self._mid_prices) < min_vol_samples:
            return 0.0
        try:
            return float(statistics.stdev(self._mid_prices))
        except statistics.StatisticsError:
            return 0.0

    def reset(self) -> None:
        self._mid_prices.clear()
        self._spreads.clear()
