from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.drawdown_controller")


class LiveDrawdownController:
    """
    Principal Drawdown Control Engine.

    Objective: Systematically protect platform capital by reducing or halting
    trading activity as portfolio drawdown escalates.

    Model: Tiered Risk Adjustment (5% / 10% / 15% Rules).
    Constraint: Principal Preservation Gating (15% Max DD Operational Lock).
    """

    def __init__(self) -> None:
        """
        Initialize the institutional drawdown controller.
        """
        # Telemetry for institutional situational awareness.
        self._historical_max_drawdown: float = 0.0
        self._cumulative_adjustment_count: int = 0

    def calculate_risk_adjustment(
        self, current_equity: float, peak_equity: float
    ) -> dict[str, Any]:
        r"""
        Produce a terminal risk adjustment report and compute the risk multiplier.

        Forensic Logic:
        1. Drawdown Computation: $DD = (Peak - Current) / Peak$.
        2. Tiered Modulation:
           - $DD \ge 15\% \implies$ Multiplier = 0.00 (STOP).
           - $DD \ge 10\% \implies$ Multiplier = 0.50 (REDUCE_50).
           - $DD \ge 5 \% \implies$ Multiplier = 0.75 (REDUCE_25).
           - Else $\implies$ Multiplier = 1.00 (NORMAL).
        """
        start_time = time.time()

        if peak_equity <= 0:
            return {
                "status": "DD_CONTROL_ERROR",
                "result": "FAIL",
                "message": "Institutional peak equity must be strictly positive.",
            }

        # 1. Industrial Drawdown Computation.
        raw_drawdown = (peak_equity - current_equity) / peak_equity
        # Ensure drawdown is non-negative for mathematical veracity.
        current_drawdown = max(0.0, raw_drawdown)

        applied_risk_factor = 1.0
        risk_action_level = "NORMAL"

        # 2. Tiered Operational Rule Evaluation (5% / 10% / 15%).
        stop_level = 0.15
        heavy_reduce = 0.10
        light_reduce = 0.05

        if current_drawdown >= stop_level:
            applied_risk_factor = 0.0
            risk_action_level = "STOP"
        elif current_drawdown >= heavy_reduce:
            applied_risk_factor = 0.5
            risk_action_level = "REDUCE_50"
        elif current_drawdown >= light_reduce:
            applied_risk_factor = 0.75
            risk_action_level = "REDUCE_25"
        else:
            applied_risk_factor = 1.0
            risk_action_level = "NORMAL"

        # 3. Telemetry Update and Forensic Indexing.
        self._historical_max_drawdown = max(self._historical_max_drawdown, current_drawdown)

        if risk_action_level != "NORMAL":
            self._cumulative_adjustment_count += 1
            _LOG.warning(
                f"[DD_CONTROL] RISK_ADJUSTED | Level: {risk_action_level} "
                f"| DD: {current_drawdown:.4f} | Factor: {applied_risk_factor}"
            )
        else:
            _LOG.info(f"[DD_CONTROL] STATE_SECURE | DD: {current_drawdown:.4f}")

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "DD_CONTROL_COMPLETE",
            "result": "PASS" if applied_risk_factor > 0 else "HALTED",
            "action": risk_action_level,
            "metrics": {
                "current_drawdown_percent": round(current_drawdown * 100, 2),
                "risk_adjustment_factor": round(applied_risk_factor, 4),
                "cumulative_actions_taken": self._cumulative_adjustment_count,
            },
            "certification": {
                "peak_drawdown_observed": round(self._historical_max_drawdown, 4),
                "timestamp": time.time(),
                "validation_latency_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_drawdown_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional principal preservation.
        """
        lockout_threshold = 0.15
        return {
            "status": "DD_GOVERNANCE",
            "maxly_historical_drawdown": round(self._historical_max_drawdown, 4),
            "governance_event_count": self._cumulative_adjustment_count,
            "lockout_active": self._historical_max_drawdown >= lockout_threshold,
        }
