from __future__ import annotations
from collections import deque


class HiddenLiquidityDetector:
    def __init__(self, window_size: int = 10) -> None:
        self._window_size = window_size
        self._history: deque[float] = deque(maxlen=window_size)
        self._last_iceberg_price: float | None = None

    def update(self, executed_vol: float, visible_depletion: float, price: float) -> float:
        try:
            epsilon = 1e-08
            if (
                executed_vol > epsilon
                and visible_depletion > epsilon
                and (executed_vol > visible_depletion + epsilon)
            ):
                h_signal = (executed_vol - visible_depletion) / executed_vol
                self._last_iceberg_price = price
            else:
                h_signal = 0.0
            self._history.append(h_signal)
            return self._aggregate_signal()
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            return 0.0

    def _aggregate_signal(self) -> float:
        if not self._history:
            return 0.0
        return sum(self._history) / len(self._history)

    def reset(self) -> None:
        self._history.clear()
        self._last_iceberg_price = None
