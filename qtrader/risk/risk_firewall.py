from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

_LOG = logging.getLogger("qtrader.risk.risk_firewall")


@dataclass(slots=True, frozen=True)
class OrderProposal:
    """
    Industrial Container for Pre-Trade Order Candidates.
    """

    symbol: str
    side: str  # BUY / SELL
    size: float
    price: float


@dataclass(slots=True, frozen=True)
class PortfolioRiskState:
    """
    Real-Time Snapshot of Portfolio Risk Metrics.
    """

    equity: float
    peak_equity: float
    volatility_annual: float
    total_exposure: float
    positions: dict[str, float]
    is_telemetry_valid: bool = True


class RiskFirewall:
    """
    Principal Hard Risk Gate.

    Acts as a terminal, non-bypassable pre-trade firewall that intercept
    every order to ensure absolute portfolio-level safety.
    """

    def __init__(
        self,
        max_var_pct: float = 0.02,  # 2% Daily VaR limit (95% CI)
        max_drawdown_pct: float = 0.15,  # 15% Total Drawdown Limit
        max_gross_leverage: float = 5.0,  # 5x Global Exposure Limit
        confidence_level: float = 1.96,  # 95% Confidence (Normal Approx)
    ) -> None:
        """
        Initialize the Firewall with institutional-grade constraints.

        Args:
            max_var_pct: Threshold for daily Value-at-Risk relative to equity.
            max_drawdown_pct: Absolute peak-to-trough loss threshold.
            max_gross_leverage: Maximum total exposure multiplier.
            confidence_level: Z-score for VaR calculation.
        """
        self._max_var = max_var_pct
        self._max_dd = max_drawdown_pct
        self._max_lev = max_gross_leverage
        self._z_score = confidence_level

        # Telemetry
        self._stats = {"blocked": 0, "reduced": 0, "allowed": 0}

    def validate_order(self, order: OrderProposal, state: PortfolioRiskState) -> dict[str, Any]:
        """
        Terminal pre-trade validation logic.

        Process:
        1. Fail-Safe: Block if telemetry is invalid.
        2. Simulation: Compute post-trade exposure and VaR.
        3. Decision: Enforce Hard Limits (BLOCK) or Capping (REDUCE).

        Returns:
            dict containing decision (ALLOW/BLOCK/REDUCE) and audit reasons.
        """
        # 0. Fail-Safe Mode
        if not state.is_telemetry_valid or state.equity <= 0:
            _LOG.error(f"BLOCK | {order.symbol} | FAIL-SAFE: Stale telemetry or insolvency")
            self._stats["blocked"] += 1
            return {"decision": "BLOCK", "reason": "STALE_TELEMETRY_OR_INSOLVENT"}

        # 1. Exposure Simulation
        order_value = abs(order.size * order.price)
        projected_exposure = state.total_exposure + order_value
        projected_leverage = projected_exposure / state.equity

        # 2. Daily VaR Projection (Parametric Normal Approximation)
        # VaR = Exposure * Z * (Vol_ann / sqrt(252))
        daily_vol = state.volatility_annual / np.sqrt(252)
        projected_var_amt = projected_exposure * self._z_score * daily_vol
        projected_var_pct = projected_var_amt / state.equity

        # 3. Drawdown Validation
        current_dd = (
            (state.peak_equity - state.equity) / state.peak_equity if state.peak_equity > 0 else 0.0
        )

        # 4. Terminal Decision Logic
        if current_dd >= self._max_dd:
            _LOG.warning(f"BLOCK | {order.symbol} | DD_BREACH: {current_dd:.2%}")
            self._stats["blocked"] += 1
            return {"decision": "BLOCK", "reason": "MAX_DRAWDOWN_EXCEEDED"}

        if projected_var_pct > self._max_var:
            _LOG.warning(f"BLOCK | {order.symbol} | VAR_BREACH: {projected_var_pct:.2%}")
            self._stats["blocked"] += 1
            return {"decision": "BLOCK", "reason": "VAR_LIMIT_EXCEEDED"}

        if projected_leverage > self._max_lev:
            # Attempt to REDUCE rather than block
            safe_exposure_limit = self._max_lev * state.equity
            allowable_additional = safe_exposure_limit - state.total_exposure

            if allowable_additional > 0:
                reduced_size = allowable_additional / order.price
                _LOG.info(f"REDUCE | {order.symbol} | LEV_BREACH: Reduced to {reduced_size:.2f}")
                self._stats["reduced"] += 1
                return {"decision": "REDUCE", "allowed_size": round(reduced_size, 4)}

            _LOG.warning(f"BLOCK | {order.symbol} | LEV_BREACH: No remaining capacity")
            self._stats["blocked"] += 1
            return {"decision": "BLOCK", "reason": "MAX_EXPOSURE_EXCEEDED"}

        self._stats["allowed"] += 1
        return {
            "decision": "ALLOW",
            "projected_var": round(projected_var_pct, 4),
            "projected_lev": round(projected_leverage, 2),
        }

    def get_risk_report(self) -> dict[str, Any]:
        """
        Generate industrial compliance telemetry.
        """
        return {
            "status": "RISK_REPORT",
            "blocked_orders": self._stats["blocked"],
            "reduced_orders": self._stats["reduced"],
            "allowed_orders": self._stats["allowed"],
        }
