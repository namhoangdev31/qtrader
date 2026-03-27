from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

_LOG = logging.getLogger("qtrader.compliance.spoof_detector")


@dataclass(slots=True)
class UserTradeStats:
    """
    Industrial accumulation of order lifecycle metrics for a specific user-symbol pair.
    """

    submitted: int = 0
    cancelled: int = 0
    filled: float = 0.0
    large_orders: int = 0
    short_lived: int = 0


class SpoofDetector:
    """
    Industrial Spoofing Detection Engine.

    Objective: Identify fake liquidity placement intended to manipulate global
    orderbook pricing without genuine intent to execute.

    Institutional Thresholds:
    1. CancelRate (CR) > 90%.
    2. FillRate (FR) < 5%.
    3. Differentiate Market Makers (who maintain non-zero fill rates).
    """

    def __init__(
        self,
        min_cancel_rate: float = 0.90,
        max_fill_rate: float = 0.05,
        min_orders: int = 10,
    ) -> None:
        """
        Initialize with institutional compliance thresholds.

        Args:
            min_cancel_rate: Proportion of orders cancelled ($C_R$).
            max_fill_rate: Proportion of orders filled relative to volume ($F_R$).
            min_orders: Sample size required before detection triggers.
        """
        self._min_c_rate: Final[float] = min_cancel_rate
        self._max_f_rate: Final[float] = max_fill_rate
        self._min_orders: Final[int] = min_orders

        # Internal registry: User -> Symbol -> Stats
        self._registry: dict[str, dict[str, UserTradeStats]] = {}

        # Telemetry for situational awareness.
        self._stats = {"spoof_flags": 0, "false_positives": 0}

    def record_event(  # noqa: PLR0913
        self,
        user_id: str,
        symbol: str,
        event_type: str,
        size: float,
        filled_qty: float,
        lifespan_s: float,
    ) -> None:
        """
        Accumulate order lifecycle statistics for forensic analysis.
        """
        if user_id not in self._registry:
            self._registry[user_id] = {}
        if symbol not in self._registry[user_id]:
            self._registry[user_id][symbol] = UserTradeStats()

        stats = self._registry[user_id][symbol]

        if event_type == "SUBMIT":
            stats.submitted += 1
            # Industrial 'Large' Baseline: > 100 units (symbol-agnostic for prototype).
            if size > 100:  # noqa: PLR2004
                stats.large_orders += 1
        elif event_type == "CANCEL":
            stats.cancelled += 1
            # Spoofing signature: Cancellation in < 200ms.
            if lifespan_s < 0.2:  # noqa: PLR2004
                stats.short_lived += 1
        elif event_type == "FILL":
            stats.filled += filled_qty

    def is_spoofing(self, user_id: str, symbol: str) -> bool:
        """
        Terminal Spoof Detection Logic.

        Decision Rules:
        1. Quorum: Minimum N orders must exist for statistical significance.
        2. Signature: $C_R > 0.90$ AND $F_R < 0.05$.
        3. Intent: Must involve large, short-lived orders to be flagged.

        Returns:
            bool: True (Spoof detected) or False.
        """
        if user_id not in self._registry or symbol not in self._registry[user_id]:
            return False

        stats = self._registry[user_id][symbol]

        # 1. Quorum Check (Prevent False Positives on small samples).
        if stats.submitted < self._min_orders:
            return False

        # 2. Metric Calculation.
        cancel_rate = stats.cancelled / stats.submitted
        # Fill rate is calculated as (Total Filled) / (Total Submitted Size).
        # We assume size=100 for non-recorded Fill sizes in this prototype.
        fill_rate = stats.filled / (stats.submitted * 10.0)

        # 3. Decision Logic - Manipulative Signature Matching.
        if cancel_rate > self._min_c_rate and fill_rate < self._max_f_rate:
            # Must also involve large, short-lived 'bait' orders.
            if stats.large_orders > 0 and stats.short_lived > (0.5 * stats.submitted):
                self._stats["spoof_flags"] += 1
                _LOG.warning(
                    f"[SPOOF_CHECK] TRIGGER | User: {user_id} | Symbol: {symbol} "
                    f"| C_Rate: {cancel_rate:.2f} | F_Rate: {fill_rate:.4f}"
                )
                return True

        return False

    def get_report(self) -> dict[str, Any]:
        """
        Generate operational situational awareness report for spoofing density.
        """
        return {
            "status": "SPOOF_CHECK",
            "spoof_flags_count": self._stats["spoof_flags"],
            "monitored_liquidity_entries": sum(
                s.submitted for syms in self._registry.values() for s in syms.values()
            ),
        }
