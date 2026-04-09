from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Final

_LOG = logging.getLogger("qtrader.compliance.position_limiter")


@dataclass(slots=True, frozen=True)
class LimitConfig:
    symbol_limit: float
    aggregate_limit: float


class PositionLimiter:
    def __init__(self, config: LimitConfig) -> None:
        self._config: Final[LimitConfig] = config
        self._blocked_orders: int = 0
        self._breached_symbols: set[str] = set()

    def validate_order(
        self,
        symbol: str,
        side: str,
        size: float,
        current_pos: float,
        all_positions: dict[str, float],
    ) -> bool:
        delta = size if side.upper() == "BUY" else -size
        target_symbol_pos = current_pos + delta
        if abs(target_symbol_pos) < abs(current_pos):
            return True
        if abs(target_symbol_pos) > self._config.symbol_limit:
            self._record_violation(symbol, "SYMBOL_CONCENTRATION_LIMIT_BREACH")
            return False
        current_aggregate = sum((abs(v) for v in all_positions.values()))
        target_aggregate = current_aggregate - abs(current_pos) + abs(target_symbol_pos)
        if target_aggregate > self._config.aggregate_limit:
            self._record_violation(symbol, "ACCOUNT_EXPOSURE_LIMIT_BREACH")
            return False
        return True

    def _record_violation(self, symbol: str, reason: str) -> None:
        self._blocked_orders += 1
        self._breached_symbols.add(symbol)
        _LOG.warning(f"[POSITION_CHECK] BREACH_BLOCKED | Symbol: {symbol} | Reason: {reason}")

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "COMPLIANCE_REPORT",
            "blocked_orders_count": self._blocked_orders,
            "symbols_with_breaches": list(self._breached_symbols),
            "aggregate_utilization_limit": self._config.aggregate_limit,
        }
