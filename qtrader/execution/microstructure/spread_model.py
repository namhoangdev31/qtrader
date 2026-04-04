from __future__ import annotations

import statistics
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


class SpreadDynamicsModel:
    r"""
    Bid-Ask Spread Dynamics Prediction Model.

    Predicts the next-tick spread ($S_{t+1}$) as a function of
    local volatility ($\sigma$) and order-book liquidity ($L$):

    S_{t+1} = S_t + alpha * sigma - beta * L

    - High volatility widens the spread (adverse selection risk).
    - High liquidity tightens the spread (market-making competition).
    """

    def __init__(self, config: ExecutionConfig) -> None:
        """
        Initialize the spread model with volatility and liquidity sensitivities.
        """
        micro_cfg = getattr(config, "microstructure", {}).get("spread_model", {})
        self._window_size = int(micro_cfg.get("window_size", 20))
        self._alpha = float(micro_cfg.get("alpha", 0.1))
        self._beta = float(micro_cfg.get("beta", 0.05))

        # History of mid-prices for volatility computation
        self._mid_prices: deque[float] = deque(maxlen=self._window_size)
        # History of spreads for moving average fallback
        self._spreads: deque[float] = deque(maxlen=self._window_size)

    def update(self, bid: float, ask: float, volume: float) -> float:
        """
        Update the model with new market data and return the predicted spread.

        Args:
            bid: Current best bid price.
            ask: Current best ask price.
            volume: Aggregate volume at best bid/ask (Liquidity L).
        """
        try:
            # 1. Calculate current metrics
            current_spread = ask - bid
            mid_price = (ask + bid) / 2.0

            # 2. Update rolling history
            self._mid_prices.append(mid_price)
            self._spreads.append(current_spread)

            # 3. Compute Features
            local_vol = self._compute_vol()
            local_liq = volume

            # 4. Predict Future Spread
            # S_{t+1} = S_t + alpha * sigma - beta * L
            # Sensitivity coefficients (alpha, beta) must be calibrated to Symbol/Asset units.
            predicted = current_spread + (self._alpha * local_vol) - (self._beta * local_liq)

            # Industrial Guardrails:
            # - Spread must be positive.
            # - Failback to current spread if data is insufficient for volatility.
            min_samples = 5
            if len(self._mid_prices) < min_samples:
                return current_spread

            # Ensure minimum tick size (or non-negativity)
            min_spread = 1e-8
            return max(min_spread, predicted)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            # High-performance silent failover for industrial-grade stability
            if self._spreads:
                return float(sum(self._spreads) / len(self._spreads))
            return 0.0

    def _compute_vol(self) -> float:
        """Calculate local mid-price volatility (standard deviation)."""
        min_vol_samples = 2
        if len(self._mid_prices) < min_vol_samples:
            return 0.0

        try:
            # Standard deviation of mid-price window
            return float(statistics.stdev(self._mid_prices))
        except statistics.StatisticsError:
            return 0.0

    def reset(self) -> None:
        """Reset the internal model state."""
        self._mid_prices.clear()
        self._spreads.clear()
