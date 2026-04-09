from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class ToxicFlowPredictor:
    def __init__(self, config: ExecutionConfig) -> None:
        micro_cfg = getattr(config, "microstructure", {}).get("toxic_flow", {})
        self._window_size = int(micro_cfg.get("window_size", 50))
        self._history: deque[tuple[int, float]] = deque(maxlen=self._window_size)

    def update(self, trade_side: int, price_move: float) -> float:
        try:
            side = 1 if trade_side > 0 else -1
            self._history.append((side, price_move))
            min_samples = 10
            if len(self._history) < min_samples:
                return 0.5
            numerator = 0.0
            denominator = 0.0
            for h_side, h_move in self._history:
                numerator += h_side * h_move
                denominator += abs(h_move)
            epsilon = 1e-12
            if denominator <= epsilon:
                return 0.5
            raw_tau = float(numerator / denominator)
            return (raw_tau + 1.0) / 2.0
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            return 0.5

    def reset(self) -> None:
        self._history.clear()
