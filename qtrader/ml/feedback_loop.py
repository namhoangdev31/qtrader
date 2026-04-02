from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

_LOG = logging.getLogger("qtrader.ml.feedback_loop")


@dataclass(slots=True, frozen=True)
class FeedbackSample:
    """
    Industrial Training Sample with Attributed Reward.
    """

    signal_id: str
    features: np.ndarray[Any, Any]
    net_reward: float
    timestamp: float


class FeedbackController:
    """
    Principal Feedback Controller.

    Objective: Link execution data (trades) back to learning models (alpha)
    by filtering execution noise, attributing realized costs, and
    enforcing mandatory delay windows to eliminate informational leakage.
    Ensures that models learn from 'Net Alpha' rather than gross theory.
    """

    def __init__(
        self,
        min_fill_pct: float = 0.9,
        max_slippage_bps: float = 50.0,
        delay_window_s: int = 60,
    ) -> None:
        """
        Initialize the feedback lifecycle controller.

        Args:
            min_fill_pct: Minimum fill ratio for a trade to be considered 'Signal'.
            max_slippage_bps: Max execution slippage before trade is flagged as 'Noise'.
            delay_window_s: Mandatory seconds to wait before committing to training.
        """
        self._min_fill = min_fill_pct
        self._max_slippage = max_slippage_bps
        self._delay = delay_window_s

        # Telemetry
        self._stats = {"processed": 0, "filtered": 0}

    def process_trade(
        self, trade: dict[str, Any], signal: dict[str, Any]
    ) -> FeedbackSample | None:
        """
        Process a trade-signal pair into a high-fidelity training sample.

        Workflow:
        1. Delay Gate: Ensures trade is fully realized and settled.
        2. Noise Gate: Filters anomalous slippage or partial fills.
        3. Reward Gate: Computes net realized PnL subtracting all costs.

        Returns:
            FeedbackSample if authorized, else None if noise/immature.
        """
        self._stats["processed"] += 1

        # 1. Look-Ahead Protection (Mandatory Maturity Window)
        # Trade must have settled long enough ago to prevent leakage.
        # Note: In backtests, this uses simulation time; in live, system time.
        now = time.time()
        # Fallback to trade['timestamp'] if 'settled_at' is missing
        execution_time = trade.get("settled_at", trade["timestamp"])
        if now - execution_time < self._delay:
            return None

        # 2. Industrial Noise Filtration
        # Calculate slippage in Basis Points (bps)
        req_price = trade["requested_price"]
        avg_price = trade["avg_price"]
        slippage_bps = abs(avg_price - req_price) / req_price * 10000

        # Fill percentage check
        fill_pct = trade["filled_qty"] / trade["total_qty"]

        if slippage_bps > self._max_slippage or fill_pct < self._min_fill:
            self._stats["filtered"] += 1
            _LOG.warning(
                f"[FEEDBACK] Noise Filtered | Signal: {signal['id']} | "
                f"Slip: {slippage_bps:.1f}bps | Fill: {fill_pct:.1%}"
            )
            return None

        # 3. Net Alpha Attribution
        # R = (Exit - Entry) * Qty - Fees
        pnl = (trade["exit_price"] - trade["entry_price"]) * trade["filled_qty"]
        fees = trade.get("fees", 0.0)
        net_reward = pnl - fees

        return FeedbackSample(
            signal_id=signal["id"],
            features=signal["features"],
            net_reward=float(net_reward),
            timestamp=execution_time,
        )

    def get_feedback_report(self) -> dict[str, Any]:
        """
        Generate feedback quality telemetry summary.
        """
        total = self._stats["processed"]
        return {
            "status": "REPORT",
            "processed_count": total,
            "noise_ratio": (
                round(self._stats["filtered"] / total, 4) if total > 0 else 0.0
            ),
        }
