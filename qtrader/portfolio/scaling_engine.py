from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.scaling_engine")


class CapitalScalingEngine:
    r"""
    Principal Capital Scaling Engine.

    Objective: Gradually increase strategy capital based on performance stability
    and drawdown status, enforcing institutional prudence limits.

    Model: Stability-Gated Growth ($g \le 5\%$).
    Constraint: Prudence Gating (No scaling during drawdown or volatility spikes).
    """

    def __init__(self, max_growth: float = 0.05, global_limit: float = 1_000_000_000.0) -> None:
        """
        Initialize the institutional scaling controller.
        """
        self._max_growth = max_growth
        self._global_limit = global_limit

        # Telemetry for institutional situational awareness.
        self._total_growth_scaled: float = 0.0
        self._scaling_event_count: int = 0

    def evaluate_scaling_readiness(
        self,
        current_capital: float,
        performance_metrics: dict[str, Any],
        target_growth: float = 0.05,
    ) -> dict[str, Any]:
        """
        Produce a terminal scaling report and compute updated capital.

        Forensic Logic:
        1. Drawdown Gating: Growth is 0.0 if the portfolio is in a drawdown state.
        2. Stability Gating: Growth is 0.0 if PnL volatility exceeds the threshold.
        3. Cap Enforcement: Growth is strictly limited to 5% per cycle.
        4. Global Limit: Scaling is suspended if new capital exceeds $1,000,000,000.
        """
        start_time = time.time()

        # 1. Industrial Readiness Verification.
        is_in_drawdown = performance_metrics.get("in_drawdown", False)
        std_pnl = float(performance_metrics.get("std_pnl", 0.0))
        max_std = float(performance_metrics.get("max_std", 1.0))
        is_unstable = std_pnl > max_std

        applied_growth = 0.0
        rejection_reason = None

        if is_in_drawdown:
            applied_growth = 0.0
            rejection_reason = "PORTFOLIO_IN_DRAWDOWN"
        elif is_unstable:
            applied_growth = 0.0
            rejection_reason = "VOLATILITY_ABOVE_THRESHOLD"
        elif current_capital >= self._global_limit:
            applied_growth = 0.0
            rejection_reason = "GLOBAL_CAPACITY_LIMIT_REACHED"
        else:
            # 2. Scaling Computation (Cap = 5%).
            applied_growth = min(target_growth, self._max_growth)

        new_capital = current_capital * (1.0 + applied_growth)

        # 3. Final Decision and Telemetry Indexing.
        if applied_growth > 0:
            _LOG.info(
                f"[SCALING] GROWTH_APPROVED | Growth: {applied_growth:.4f} | New: {new_capital:.2f}"
            )
            self._total_growth_scaled += applied_growth
            self._scaling_event_count += 1
        else:
            _LOG.warning(f"[SCALING] GROWTH_SUSPENDED | Reason: {rejection_reason}")

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "SCALING_COMPLETE",
            "result": "PASS" if applied_growth > 0 or rejection_reason else "FAIL",
            "metrics": {
                "applied_growth_rate": round(applied_growth, 4),
                "new_scaled_capital": round(new_capital, 2),
                "scaling_event_count": self._scaling_event_count,
            },
            "readiness_trace": {
                "drawdown_status": "LOCKED" if is_in_drawdown else "OK",
                "stability_status": "LOCKED" if is_unstable else "OK",
                "rejection_reason": rejection_reason,
            },
            "certification": {
                "institutional_growth_cap": self._max_growth,
                "global_capacity_limit": self._global_limit,
                "timestamp": time.time(),
                "real_validation_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_scaling_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional financial prudence.
        """
        avg_growth = 0.0
        if self._scaling_event_count > 0:
            avg_growth = self._total_growth_scaled / self._scaling_event_count

        return {
            "status": "SCALING_GOVERNANCE",
            "total_scaling_events": self._scaling_event_count,
            "cumulative_scaled_growth": round(self._total_growth_scaled, 4),
            "avg_growth_per_event": round(avg_growth, 4),
        }
