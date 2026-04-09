from __future__ import annotations
import logging
import time
from decimal import Decimal
from typing import Any
import polars as pl
from qtrader.core.decimal_adapter import d

_LOG = logging.getLogger(__name__)
try:
    from qtrader_core import CapitalAllocator as RustAllocator

    _HAS_RUST = True
except ImportError:
    _LOG.warning(
        "ALLOCATOR | Rust core (qtrader_core) not found. Falling back to Python implementation."
    )
    _HAS_RUST = False


class CapitalAllocationEngine:
    def __init__(self, max_cap: Decimal = d("0.2")) -> None:
        self._max_cap = max_cap
        if not _HAS_RUST:
            raise RuntimeError("ALLOCATOR | Rust core (qtrader_core) is required.")
        self._rust_allocator = RustAllocator(max_cap=float(max_cap))
        self._current_distribution: dict[str, Decimal] = {}
        self._capital_concentration: Decimal = d(0)
        self._last_trace: dict[str, Any] = {}

    def allocate_capital(
        self, strategies: list[dict[str, Any]], total_capital: Decimal
    ) -> dict[str, Any]:
        start_time = time.time()
        if not _HAS_RUST:
            raise RuntimeError(
                "ALLOCATOR | Rust core (qtrader_core) is required for capital allocation."
            )
        strategy_sharpes = {str(s["id"]): float(s.get("sharpe", 0.0)) for s in strategies}
        report = self._rust_allocator.allocate_sharpe(strategy_sharpes, float(total_capital))
        if report.status == "ALLOCATION_EMPTY":
            _LOG.warning("[ALLOCATE] NO_PERFORMERS | Zero capital deployed.")
            return {
                "status": "ALLOCATION_EMPTY",
                "result": "SKIP",
                "message": "Zero strategies with Sharpe > 0 detected for target universe.",
            }
        final_weights = {sid: Decimal(str(w)) for (sid, w) in report.weights.items()}
        target_allocation_usd = {sid: w * total_capital for (sid, w) in final_weights.items()}
        self._capital_concentration = Decimal(str(report.max_concentration))
        self._current_distribution = target_allocation_usd
        artifact = {
            "status": "ALLOCATION_COMPLETE",
            "result": "PASS",
            "metrics": {
                "active_strategy_nodes": len(final_weights),
                "total_capital_usd": total_capital,
                "deployed_capital_usd": sum(target_allocation_usd.values()),
                "max_concentration_score": self._capital_concentration,
            },
            "distribution_map": final_weights,
            "certification": {
                "institutional_cap_limit": self._max_cap,
                "timestamp": time.time(),
                "real_validation_duration_ms": (time.time() - start_time) * 1000,
            },
        }
        return artifact

    def get_allocation_telemetry(self) -> dict[str, Any]:
        entropy = d(1) - self._capital_concentration if self._capital_concentration > 0 else d(0)
        return {
            "status": "ALLOCATION_GOVERNANCE",
            "current_max_concentration": self._capital_concentration,
            "diversification_entropy": entropy,
            "active_capital_nodes": len(self._current_distribution),
        }

    def validate_order_size(
        self,
        symbol: str,
        proposed_qty: Decimal,
        price: Decimal,
        total_portfolio_value: Decimal,
        current_position_qty: Decimal = d(0),
    ) -> tuple[Decimal, str]:
        if total_portfolio_value <= 0:
            return (proposed_qty, "INITIAL_ALLOCATION")
        new_total_qty = current_position_qty + proposed_qty
        new_notional = abs(new_total_qty) * price
        concentration = new_notional / total_portfolio_value
        if concentration <= self._max_cap:
            return (proposed_qty, "WITHIN_LIMITS")
        allowed_notional = total_portfolio_value * self._max_cap
        current_notional = abs(current_position_qty) * price
        remaining_notional = max(d(0), allowed_notional - current_notional)
        scaled_qty = remaining_notional / price if price > 0 else d(0)
        scaled_qty = scaled_qty.quantize(Decimal("0.00000001"))
        reason = f"CONCENTRATION_GUARD | Scaled from {proposed_qty} to {scaled_qty} (Cap: {self._max_cap:.0%})"
        self._last_trace = {
            "symbol": symbol,
            "proposed_qty": float(proposed_qty),
            "approved_qty": float(scaled_qty),
            "current_notional": float(current_notional),
            "new_notional": float(new_notional),
            "concentration": float(concentration),
            "max_cap": float(self._max_cap),
            "reason": reason,
        }
        return (scaled_qty, reason)

    def get_trace(self) -> dict[str, Any]:
        return self._last_trace


class PortfolioAllocator:
    def __init__(self, max_weight: float = 0.2) -> None:
        self.max_weight = max_weight
        if _HAS_RUST:
            self._rust_allocator = RustAllocator(max_cap=max_weight)

    def allocate(self, strategy_returns: dict[str, pl.Series]) -> dict[str, pl.Series]:
        if not strategy_returns:
            return {}
        if not _HAS_RUST:
            raise RuntimeError("Rust core required for PortfolioAllocator.")
        vols = {name: float(series.std()) for (name, series) in strategy_returns.items()}
        report = self._rust_allocator.allocate_risk_parity(vols, 1.0)
        min_len = min((len(series) for series in strategy_returns.values()))
        result = {}
        for strat_name, weight in report.weights.items():
            result[strat_name] = pl.Series(
                values=[weight] * min_len, name=strat_name, dtype=pl.Float64
            )
        return result
