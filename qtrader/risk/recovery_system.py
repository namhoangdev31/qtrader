from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

_LOG = logging.getLogger("qtrader.risk.recovery_system")


class RecoveryAction(str, Enum):
    HALT_TRADING = "HALT_TRADING"
    ISOLATE_STRATEGY = "ISOLATE_STRATEGY"
    REDUCE_EXPOSURE = "REDUCE_EXPOSURE"
    NOTIFY_ONLY = "NOTIFY_ONLY"
    NO_ACTION = "NO_ACTION"


@dataclass(slots=True, frozen=True)
class FailureEvent:
    strategy_id: str | None
    pnl_drawdown: float
    is_risk_high: bool
    is_system_fault: bool
    description: str


class RecoverySystem:
    def __init__(self, loss_limit: float = -5000.0) -> None:
        self._loss_limit = loss_limit
        self._stats = {"recovery_count": 0, "last_recovery_time": 0.0}

    def propose_recovery(self, event: FailureEvent) -> dict[str, Any]:
        start_time = time.perf_counter()
        if event.is_system_fault:
            action = RecoveryAction.HALT_TRADING
            reason = f"CRITICAL_SYSTEM_FAULT: {event.description}"
        elif event.pnl_drawdown <= self._loss_limit:
            action = RecoveryAction.ISOLATE_STRATEGY
            reason = f"TERMINAL_PNL_BREACH: {event.pnl_drawdown:.2f}"
        elif event.is_risk_high:
            action = RecoveryAction.REDUCE_EXPOSURE
            reason = f"RISK_DEGRADATION_DETECTED: {event.description}"
        else:
            action = RecoveryAction.NO_ACTION
            reason = "NORMAL_OPERATING_CONDITIONS"
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
        return {
            "status": "REPORT",
            "total_recoveries": self._stats["recovery_count"],
            "last_recovery_latency_ms": round(self._stats["last_recovery_time"], 4),
        }
