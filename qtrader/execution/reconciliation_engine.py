"""Deterministic reconciliation engine for position consistency."""

from __future__ import annotations

from typing import Dict, Any


class ReconciliationEngine:
    """Engine for deterministic position reconciliation between local OMS and exchange."""

    def __init__(self, tolerance: float = 1e-8) -> None:
        """Initialize reconciliation engine.

        Args:
            tolerance: Maximum allowed absolute difference before considering it a mismatch.
        """
        self.tolerance = tolerance

    def reconcile(
        self, local_positions: Dict[str, float], exchange_positions: Dict[str, float]
    ) -> Dict[str, Any]:
        """Reconcile positions between local OMS and exchange.

        Args:
            local_positions: Dictionary of symbol -> position from local OMS.
            exchange_positions: Dictionary of symbol -> position from exchange.

        Returns:
            Dictionary with reconciliation result:
                {
                    "status": "OK" | "MISMATCH",
                    "symbol_diff": Dict[str, float],
                    "total_abs_diff": float
                }
        """
        # Compute differences for all symbols in union of keys
        all_symbols = set(local_positions.keys()) | set(exchange_positions.keys())
        symbol_diff: Dict[str, float] = {}
        total_abs_diff = 0.0

        for symbol in all_symbols:
            local_qty = local_positions.get(symbol, 0.0)
            exchange_qty = exchange_positions.get(symbol, 0.0)
            diff = local_qty - exchange_qty
            symbol_diff[symbol] = diff
            total_abs_diff += abs(diff)

        status = "MISMATCH" if total_abs_diff > self.tolerance else "OK"

        return {"status": status, "symbol_diff": symbol_diff, "total_abs_diff": total_abs_diff}
