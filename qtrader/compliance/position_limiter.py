from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

_LOG = logging.getLogger("qtrader.compliance.position_limiter")


@dataclass(slots=True, frozen=True)
class LimitConfig:
    """
    Industrial Structural Limit Configuration.
    Aggregates exchange-mandated and regulatory constraints.
    """

    symbol_limit: float  # Institutional Cap per Symbol (min of Exchange vs Regulatory)
    aggregate_limit: float  # Platform-wide total exposure limit


class PositionLimiter:
    r"""
    Principal Position Limit Enforcement Engine.

    Objective: Enforce structural exposure caps across individual symbols and
    account-wide aggregate dimensions.

    Operational Mode: Pre-trade 'Hard Gate' (Programmatically Un-bypassable).
    Complies with global market integrity and concentration directives.
    """

    def __init__(self, config: LimitConfig) -> None:
        """
        Initialize with institutional limit constraints.
        """
        self._config: Final[LimitConfig] = config

        # Telemetry for compliance situational awareness.
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
        r"""
        Execute pre-trade structural compliance verification.

        Verification logic:
        1. Offsetting Check: If order reduces $|Position|$, it's risk-reducing (ALWAYS ALLOW).
        2. Per-Symbol Limit: Verifies $|current\_pos + \delta| \le L_{symbol}$.
        3. Aggregate Exposure: Verifies $\sum_{i} |Position_i| \le L_{aggregate}$.

        Returns:
            bool: True if order is compliant (ALLOWED), else False (BLOCKED).
        """
        # Industrial Delta Calculation
        delta = size if side.upper() == "BUY" else -size
        target_symbol_pos = current_pos + delta

        # 1. Quaternary Intelligence: Offsetting Exception
        # Constraint: Risk-reducing orders (closing positions) are immune to limits.
        if abs(target_symbol_pos) < abs(current_pos):
            return True

        # 2. Structural per-symbol compliance check.
        if abs(target_symbol_pos) > self._config.symbol_limit:
            self._record_violation(symbol, "SYMBOL_CONCENTRATION_LIMIT_BREACH")
            return False

        # 3. Aggregate Exposure Compliance verification.
        current_aggregate = sum(abs(v) for v in all_positions.values())
        # Recompute aggregate state assuming fill.
        target_aggregate = current_aggregate - abs(current_pos) + abs(target_symbol_pos)

        if target_aggregate > self._config.aggregate_limit:
            self._record_violation(symbol, "ACCOUNT_EXPOSURE_LIMIT_BREACH")
            return False

        return True

    def _record_violation(self, symbol: str, reason: str) -> None:
        """
        Deterministic Audit Trail for blocked order interventions.
        """
        self._blocked_orders += 1
        self._breached_symbols.add(symbol)
        _LOG.warning(f"[POSITION_CHECK] BREACH_BLOCKED | Symbol: {symbol} | Reason: {reason}")

    def get_report(self) -> dict[str, Any]:
        """
        Generate operational governance situational awareness report.
        """
        return {
            "status": "COMPLIANCE_REPORT",
            "blocked_orders_count": self._blocked_orders,
            "symbols_with_breaches": list(self._breached_symbols),
            "aggregate_utilization_limit": self._config.aggregate_limit,
        }
