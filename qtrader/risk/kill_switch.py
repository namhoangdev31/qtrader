from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.risk.kill_switch")


class GlobalKillSwitch:
    r"""
    Principal Institutional Safety Mechanism.

    Objective: Immediately stop all trading activity under catastrophic conditions
    (e.g., severe drawdown, critical capital loss, or high-intensity system anomaly).

    Model: Boolean Kill-Condition ($K = (DD > DD_{crit}) \lor (Loss > Loss_{max})$
           $\lor (A > A_{crit})$).
    Constraint: Sub-millisecond execution. No override after trigger.
    """

    def __init__(
        self,
        dd_limit: float = 0.20,
        loss_limit: float = 1_000_000.0,
        anomaly_limit: float = 0.95,
    ) -> None:
        """
        Initialize the institutional kill switch.

        Parameters:
        - dd_limit: Critical drawdown threshold (e.g., 0.20 = 20%).
        - loss_limit: Maximum absolute capital loss (e.g., USD).
        - anomaly_limit: Critical anomaly score threshold.
        """
        self._dd_limit = dd_limit
        self._loss_limit = loss_limit
        self._anomaly_limit = anomaly_limit

        # Persistent state for platform finality.
        self._is_system_halted: bool = False
        self._kill_timestamp: float = 0.0
        self._kill_reason: str = ""

    def evaluate_kill_system(
        self,
        current_drawdown: float,
        current_absolute_loss: float,
        current_anomaly_score: float,
        manual_trigger: bool = False,
    ) -> dict[str, Any]:
        """
        Evaluate kill conditions and trigger non-overrideable safety sequence.

        Forensic Logic:
        1. State Gating: Returns existing halt state if already triggered.
        2. Boolean Verification (K): Evaluates DD, Loss, Anomaly, and Manual flags.
        3. Safety Action Selection: Triggers global cancellation and liquidation.
        """
        eval_start = time.time()

        # 1. State Gating (Immutability check).
        if self._is_system_halted:
            return {
                "status": "ALREADY_HALTED",
                "reason": self._kill_reason,
                "timestamp": self._kill_timestamp,
            }

        # 2. Boolean Kill-Logic (K).
        kill_triggered = False
        reason = ""

        if current_drawdown >= self._dd_limit:
            kill_triggered = True
            reason = f"CRITICAL_DRAWDOWN_BREACH: {current_drawdown:.2%}"
        elif current_absolute_loss >= self._loss_limit:
            kill_triggered = True
            reason = f"MAX_LOSS_EXCEEDED: {current_absolute_loss:,.2f}"
        elif current_anomaly_score >= self._anomaly_limit:
            kill_triggered = True
            reason = f"SEVERE_ANOMALY_INTENSITY: {current_anomaly_score:.2f}"
        elif manual_trigger:
            kill_triggered = True
            reason = "INSTITUTIONAL_MANUAL_HALT_REQUEST"

        # 3. Execution (The Final Platforms Shutdown).
        if kill_triggered:
            self._is_system_halted = True
            self._kill_reason = reason
            self._kill_timestamp = time.time()

            _LOG.critical(
                f"[KILL_SWITCH] TRIGGERED | {reason} | SHUTDOWN_SEQUENCE_INITIATED "
                f"| NAV_LOSS: {current_absolute_loss:,.2f}"
            )

        latency_ms = (time.time() - eval_start) * 1000

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "KILL_SWITCH_ACTIVE" if kill_triggered else "KILL_SWITCH_RUNNING",
            "state": {
                "is_halted": self._is_system_halted,
                "kill_reason": self._kill_reason,
                "shutdown_timestamp": self._kill_timestamp,
            },
            "safety_action_manifest": [
                "CANCEL_ALL_OPEN_ORDERS_GLOBAL",
                "LIQUIDATE_ALL_POSITIONS_MARKET",
                "DISABLE_TRADING_ENGINE_DAEMON",
            ]
            if kill_triggered
            else [],
            "forensics": {
                "eval_latency_ms": round(latency_ms, 4),
                "peak_drawdown_evaluated": round(current_drawdown, 4),
            },
        }

        return artifact

    def get_kill_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional safety control.
        """
        return {
            "status": "CAPITAL_GOVERNANCE",
            "is_system_halted": self._is_system_halted,
            "kill_reason_captured": self._kill_reason,
            "halt_timestamp": self._kill_timestamp,
        }
