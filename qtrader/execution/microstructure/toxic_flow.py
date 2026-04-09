from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class ToxicFlowPredictor:
    """
    Toxic Flow (Informed Trading) Prediction Model.

    Identifies adverse selection risk by calculating the directional
    consistency between aggressive trade flow and subsequent price impact.

    Toxicity Score τ ∈ [0, 1]:
    - τ → 1.0: Highly Toxic (trades predict impact accurately).
    - τ → 0.5: Random Noise (no correlation).
    - τ → 0.0: Mean Reverting (trades predict opposite impact).
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the predictor with calibrated toxicity parameters.
        """
        micro_cfg = getattr(config, "microstructure", {}).get("toxic_flow", {})
        self._window_size = int(micro_cfg.get("window_size", 50))

        # History of [trade_side, subsequent_price_move]
        self._history: deque[tuple[int, float]] = deque(maxlen=self._window_size)

    def update(self, trade_side: int, price_move: float) -> float:
        """
        Update the toxicity model with a new trade-impact pair.

        Args:
            trade_side: 1 for Buy, -1 for Sell (aggressive side).
            price_move: Immediate price pct_change following the trade.
        """
        try:
            # 1. Update rolling history
            # trade_side must be 1 or -1
            side = 1 if trade_side > 0 else -1
            self._history.append((side, price_move))

            # 2. Compute Directional Consistency (τ)
            # τ = Σ(side_i * price_move_i) / Σ|price_move_i|
            # This measures how much of the "impact" followed the trade direction.
            min_samples = 10
            if len(self._history) < min_samples:
                # Neutral starting point for insufficient data
                return 0.5

            numerator = 0.0
            denominator = 0.0

            for h_side, h_move in self._history:
                numerator += h_side * h_move
                denominator += abs(h_move)

            epsilon = 1e-12
            if denominator <= epsilon:
                return 0.5

            # 3. Normalize to [0, 1] range:
            # raw_tau = 1.0 (Informed), 0.0 (Noise), -1.0 (Mean-Reverting)
            raw_tau = float(numerator / denominator)

            # Map [-1.0, 1.0] -> [0.0, 1.0]
            # Toxic Score τ
            return (raw_tau + 1.0) / 2.0

        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            # High-performance silent failover for industrial-grade stability
            return 0.5

    def reset(self) -> None:
        """Reset the internal detector state."""
        self._history.clear()
