from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

import numpy as np

from qtrader.core.events import ExecutionStateEvent, ExecutionStatePayload
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus


class StateBuilder:
    """
    Industrial Microstructure State Vector Builder (S_t).

    Constructs a normalized, 7-dimensional representation of the market
    for high-frequency execution optimization and RL agents:
    1. Spread (Normalized)
    2. Book Imbalance [-1, 1]
    3. Microprice (Relative to Mid)
    4. Volatility (Normalized)
    5. Queue Position [0, 1]
    6. Fill Probability [0, 1]
    7. Latency (Normalized)
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        """
        Initialize the state builder.
        """
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

        # Adaptive Normalization Bounds (Heuristic Defaults)
        self._max_spread = 0.005  # 50bps
        self._max_vol = 0.05  # 5%
        self._max_latency = 100.0  # 100ms

    async def build(self, market_state: dict[str, Any], symbol: str, venue: str) -> list[float]:
        """
        Build the 7-dimensional execution state vector S_t.
        """
        try:
            # 1. Raw Feature Extraction
            bid = float(market_state.get("bid", 0.0))
            ask = float(market_state.get("ask", 0.0))
            bid_size = float(market_state.get("bid_size", 1.0))
            ask_size = float(market_state.get("ask_size", 1.0))
            vol = float(market_state.get("volatility", 0.0))
            latency = float(market_state.get("latency", 0.0))

            if ask <= 0 or bid <= 0:
                return [0.0] * 7

            # 2. Microstructure Calculations
            mid = (bid + ask) / 2.0
            spread = (ask - bid) / mid
            imbalance = (bid_size - ask_size) / (bid_size + ask_size)
            micro_price = (bid * ask_size + ask * bid_size) / (bid_size + ask_size)

            # 3. Probability & Estimation Logic
            queue_pos = self._estimate_queue_pos(market_state)
            fill_prob = self._estimate_fill_prob(imbalance, spread)

            # 4. Normalization Pipeline
            s_spread = min(spread / self._max_spread, 1.0)
            s_imbalance = imbalance
            s_micro = (micro_price - mid) / (ask - bid) if ask > bid else 0.0
            s_vol = min(vol / self._max_vol, 1.0)
            s_queue = queue_pos
            s_fill = fill_prob
            s_latency = min(latency / self._max_latency, 1.0)

            state_vector = [
                float(s_spread),
                float(s_imbalance),
                float(s_micro),
                float(s_vol),
                float(s_queue),
                float(s_fill),
                float(s_latency),
            ]

            # 5. Auditing & Reporting
            if self._event_bus:
                event = ExecutionStateEvent(
                    trace_id=self._system_trace,
                    source="StateBuilder",
                    payload=ExecutionStatePayload(
                        symbol=symbol,
                        venue=venue,
                        state_vector=state_vector,
                        features={
                            "spread_pct": spread,
                            "imbalance": imbalance,
                            "micro_price": micro_price,
                            "volatility": vol,
                            "fill_prob": fill_prob,
                            "latency": latency,
                        },
                        metadata={"timestamp_ms": int(time.time() * 1000)},
                    ),
                )
                await self._event_bus.publish(event)

            return state_vector

        except Exception as e:
            logger.error(f"STATE_BUILDER_FAILURE | {symbol} | {e!s}")
            return [0.0] * 7

    def _estimate_queue_pos(self, state: dict[str, Any]) -> float:
        """Estimate relative queue position [0, 1] using volume density."""
        # Simple heuristic: if we don't have our own order state, assume mid-queue (0.5)
        return float(state.get("queue_pos_estimate", 0.5))

    def _estimate_fill_prob(self, imbalance: float, spread: float) -> float:
        """Heuristic fill probability based on book pressure and cost."""
        # Higher pressure on your side = higher fill prob for limit orders
        base_prob = 0.5 + (0.5 * imbalance)
        # Wider spreads decrease short-term fill probability
        spread_penalty = min(spread * 100.0, 0.4)
        return float(np.clip(base_prob - spread_penalty, 0.0, 1.0))
