from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

_LOG = logging.getLogger("qtrader.compliance.spoof_detector")


@dataclass(slots=True)
class UserTradeStats:
    submitted: int = 0
    cancelled: int = 0
    filled: float = 0.0
    large_orders: int = 0
    short_lived: int = 0


class SpoofDetector:
    def __init__(
        self, min_cancel_rate: float = 0.9, max_fill_rate: float = 0.05, min_orders: int = 10
    ) -> None:
        self._min_c_rate: Final[float] = min_cancel_rate
        self._max_f_rate: Final[float] = max_fill_rate
        self._min_orders: Final[int] = min_orders
        self._registry: dict[str, dict[str, UserTradeStats]] = {}
        self._stats = {"spoof_flags": 0, "false_positives": 0}

    def record_event(
        self,
        user_id: str,
        symbol: str,
        event_type: str,
        size: float,
        filled_qty: float,
        lifespan_s: float,
    ) -> None:
        if user_id not in self._registry:
            self._registry[user_id] = {}
        if symbol not in self._registry[user_id]:
            self._registry[user_id][symbol] = UserTradeStats()
        stats = self._registry[user_id][symbol]
        if event_type == "SUBMIT":
            stats.submitted += 1
            if size > 100:
                stats.large_orders += 1
        elif event_type == "CANCEL":
            stats.cancelled += 1
            if lifespan_s < 0.2:
                stats.short_lived += 1
        elif event_type == "FILL":
            stats.filled += filled_qty

    def is_spoofing(self, user_id: str, symbol: str) -> bool:
        if user_id not in self._registry or symbol not in self._registry[user_id]:
            return False
        stats = self._registry[user_id][symbol]
        if stats.submitted < self._min_orders:
            return False
        cancel_rate = stats.cancelled / stats.submitted
        fill_rate = stats.filled / (stats.submitted * 10.0)
        if cancel_rate > self._min_c_rate and fill_rate < self._max_f_rate:
            if stats.large_orders > 0 and stats.short_lived > 0.5 * stats.submitted:
                self._stats["spoof_flags"] += 1
                _LOG.warning(
                    f"[SPOOF_CHECK] TRIGGER | User: {user_id} | Symbol: {symbol} | C_Rate: {cancel_rate:.2f} | F_Rate: {fill_rate:.4f}"
                )
                return True
        return False

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "SPOOF_CHECK",
            "spoof_flags_count": self._stats["spoof_flags"],
            "monitored_liquidity_entries": sum(
                s.submitted for syms in self._registry.values() for s in syms.values()
            ),
        }
