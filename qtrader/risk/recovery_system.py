from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

_LOG = logging.getLogger("qtrader.risk.recovery_system")


class RecoveryAction(str, Enum):
    """
    Industrial Autonomous Recovery Actions.
    """

    HALT_TRADING = "HALT_TRADING"
    ISOLATE_STRATEGY = "ISOLATE_STRATEGY"
    REDUCE_EXPOSURE = "REDUCE_EXPOSURE"
    NOTIFY_ONLY = "NOTIFY_ONLY"
    NO_ACTION = "NO_ACTION"


@dataclass(slots=True, frozen=True)
class FailureEvent:
    """
    Snapshot of a System or Strategic Anomaly.
    """

    strategy_id: str | None
    pnl_drawdown: float  # Absolute PnL for the current period
    is_risk_high: bool  # Flag for non-terminal risk degradation
    is_system_fault: bool  # Flag for infrastructure/connectivity fault
    description: str


class RecoverySystem:
    """
    Principal Recovery Controller.

    Objective: Deterministically restore the system to a safe state
    after an anomaly by rolling back faulty strategies or isolating risk.
    Operates with zero human dependency and sub-second response times.
    """

    def __init__(self, loss_limit: float = -5000.0) -> None:
        """
        Initialize the recovery controller.

        Args:
            loss_limit: Absolute loss threshold for strategy termination.
        """
        self._loss_limit = loss_limit

        # Telemetry
        self._stats = {"recovery_count": 0, "last_recovery_time": 0.0}

    def propose_recovery(self, event: FailureEvent) -> dict[str, Any]:
        """
        Evaluate a failure signal and authorize the optimal recovery action.

        Args:
            event: Failure metadata from the MonitoringEngine.

        Returns:
            dict containing authorized recovery action and logic justification.
        """
        start_time = time.perf_counter()

        # 1. Critical System Path -> Global Halt
        if event.is_system_fault:
            action = RecoveryAction.HALT_TRADING
            reason = f"CRITICAL_SYSTEM_FAULT: {event.description}"

        # 2. Strategy Terminal Path -> Isolation (State: KILLED)
        elif event.pnl_drawdown <= self._loss_limit:
            action = RecoveryAction.ISOLATE_STRATEGY
            reason = f"TERMINAL_PNL_BREACH: {event.pnl_drawdown:.2f}"

        # 3. High Risk Warning -> Proactive Exposure Containment
        elif event.is_risk_high:
            action = RecoveryAction.REDUCE_EXPOSURE
            reason = f"RISK_DEGRADATION_DETECTED: {event.description}"

        else:
            action = RecoveryAction.NO_ACTION
            reason = "NORMAL_OPERATING_CONDITIONS"

        # Telemetry & Logging
        latency_ms = (time.perf_counter() - start_time) * 1000
        if action != RecoveryAction.NO_ACTION:
            self._stats["recovery_count"] += 1
            self._stats["last_recovery_time"] = latency_ms
            _LOG.warning(f"[RECOVERY] {action} | {event.strategy_id} | {reason}")

        return {
            "status": "RECOVERY",
            "action": action.value,
            "reason": reason,
            "strategy_id": event.strategy_id,
            "latency_ms": round(latency_ms, 4),
        }

    def get_recovery_report(self) -> dict[str, Any]:
        """
        Generate high-level recovery telemetry.
        """
        return {
            "status": "REPORT",
            "total_recoveries": self._stats["recovery_count"],
            "last_recovery_latency_ms": round(self._stats["last_recovery_time"], 4),
        }
