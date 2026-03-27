from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.execution.degradation_handler")


class ExecutionDegradationHandler:
    r"""
    Principal Execution Degradation Control System.

    Objective: Monitor execution health and dynamically react to deteriorating
    conditions (High slippage, Low fill rate, Latency spikes).

    Model: Multi-Factor Degradation Score ($D = w1 \cdot S + w2 \cdot (1-F) + w3 \cdot L$).
    Actions: NORMAL, DELAY_EXECUTION, REDUCE_SIZE, PAUSE_STRATEGY.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional degradation handler.
        """
        # Industrial Metrological Weights.
        self._w_slippage = 0.5  # Weight on normalized adverse slippage.
        self._w_fillrate = 0.3  # Weight on missed fill percentage.
        self._w_latency = 0.2  # Weight on normalized latency spikes.

        # Telemetry for institutional situational awareness.
        self._action_trigger_count: dict[str, int] = {}
        self._peak_degradation_observed: float = 0.0

    def evaluate_execution_health(
        self, current_metrics: dict[str, Any], strategy_id: str = "GLOBAL"
    ) -> dict[str, Any]:
        r"""
        Produce a terminal health report and trigger tiered reactive actions.

        Forensic Logic:
        1. Composite Score Calculation ($D$):
           - $S_{norm}$: Adverse Slippage normalized by a 20bps threshold.
           - $F_{norm}$: Missed fill percentage ($1 - FillRate$).
           - $L_{norm}$: Latency normalized by a 200ms threshold.
        2. Tiered Action Gating:
           - $D \ge 1.0 \implies$ PAUSE_STRATEGY.
           - $D \ge 0.5 \implies$ REDUCE_SIZE.
           - $D \ge 0.2 \implies$ DELAY_EXECUTION.
           - else $\implies$ NORMAL_OPERATIONS.
        """
        evaluation_start = time.time()

        # 1. Metrological Normalization.
        slippage_bps = float(current_metrics.get("slippage_bps", 0.0))
        fill_rate = float(current_metrics.get("cumulative_fill_rate", 1.0))
        latency_ms = float(current_metrics.get("recorded_latency_ms", 0.0))

        # S_norm: Adverse slippage (negative) contributes to degradation.
        # Normalized such that 20bps adverse = 1.0.
        s_norm = max(0.0, -slippage_bps / 20.0) if slippage_bps < 0 else 0.0
        # F_norm: 100% missed fill = 1.0.
        f_norm = 1.0 - fill_rate
        # L_norm: 200ms latency = 1.0.
        l_norm = min(1.0, latency_ms / 200.0)

        # Composite Score Calculation.
        degradation_score = (
            (self._w_slippage * s_norm) + (self._w_fillrate * f_norm) + (self._w_latency * l_norm)
        )

        # 2. Tiered Reactive Control.
        critical_threshold = 1.0
        high_threshold = 0.5
        elevated_threshold = 0.2
        selected_action = "NORMAL_OPERATIONS"
        if degradation_score >= critical_threshold:
            selected_action = "PAUSE_STRATEGY"
        elif degradation_score >= high_threshold:
            selected_action = "REDUCE_SIZE"
        elif degradation_score >= elevated_threshold:
            selected_action = "DELAY_EXECUTION"

        # 3. Telemetry Indexing.
        self._peak_degradation_observed = max(self._peak_degradation_observed, degradation_score)
        self._action_trigger_count[selected_action] = (
            self._action_trigger_count.get(selected_action, 0) + 1
        )

        if selected_action != "NORMAL_OPERATIONS":
            _LOG.warning(
                f"[DEGRADATION] ACTION_TRIGGERED | Action: {selected_action} "
                f"| Score: {degradation_score:.4f} | Strat: {strategy_id}"
            )

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "HEALTH_EVALUATED",
            "triggered_action": selected_action,
            "metrics": {
                "composite_degradation_score": round(degradation_score, 4),
                "peak_degradation_observed": round(self._peak_degradation_observed, 4),
            },
            "normalization": {
                "adverse_slippage_factor": round(s_norm, 4),
                "missed_fill_factor": round(f_norm, 4),
                "latency_spike_factor": round(l_norm, 4),
            },
            "certification": {
                "strategy_id": strategy_id,
                "timestamp": time.time(),
                "reaction_latency_ms": round((time.time() - evaluation_start) * 1000, 4),
            },
        }

        return artifact

    def get_degradation_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional execution health recovery.
        """
        recovery_threshold = 0.5
        return {
            "status": "DEGRADATION_GOVERNANCE",
            "peak_degradation_captured": round(self._peak_degradation_observed, 4),
            "triggered_actions_summary": self._action_trigger_count,
            "governance_regime": (
                "NOMINAL"
                if self._peak_degradation_observed < recovery_threshold
                else "REBUILDING_LIQUIDITY"
            ),
        }
