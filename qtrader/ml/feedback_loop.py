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
    signal_id: str
    features: np.ndarray[Any, Any]
    net_reward: float
    timestamp: float


class FeedbackController:
    def __init__(
        self, min_fill_pct: float = 0.9, max_slippage_bps: float = 50.0, delay_window_s: int = 60
    ) -> None:
        self._min_fill = min_fill_pct
        self._max_slippage = max_slippage_bps
        self._delay = delay_window_s
        self._stats = {"processed": 0, "filtered": 0}

    def process_trade(self, trade: dict[str, Any], signal: dict[str, Any]) -> FeedbackSample | None:
        self._stats["processed"] += 1
        now = time.time()
        execution_time = trade.get("settled_at", trade["timestamp"])
        if now - execution_time < self._delay:
            return None
        req_price = trade["requested_price"]
        avg_price = trade["avg_price"]
        slippage_bps = abs(avg_price - req_price) / req_price * 10000
        fill_pct = trade["filled_qty"] / trade["total_qty"]
        if slippage_bps > self._max_slippage or fill_pct < self._min_fill:
            self._stats["filtered"] += 1
            _LOG.warning(
                f"[FEEDBACK] Noise Filtered | Signal: {signal['id']} | Slip: {slippage_bps:.1f}bps | Fill: {fill_pct:.1%}"
            )
            return None
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
        total = self._stats["processed"]
        return {
            "status": "REPORT",
            "processed_count": total,
            "noise_ratio": round(self._stats["filtered"] / total, 4) if total > 0 else 0.0,
        }
