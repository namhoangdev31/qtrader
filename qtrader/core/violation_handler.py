from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from qtrader.alerts.alert_engine import alert_engine
from qtrader.core.container import container

if TYPE_CHECKING:
    from qtrader.core.exceptions import ConstraintViolation


class ViolationHandler:
    """
    Sovereign Violation Handler (Phase -1.5 G6_P3).
    Responsible for deterministic reaction to constraint violations.
    Ensures all violations are logged, alerted, and trigger system-wide security halts.
    """

    def __init__(self, log_path: str = "qtrader/logs/violation_log.json") -> None:
        self.logger = container.get("logger")
        self.failfast = container.get("failfast")
        self.log_path = log_path

        # Internal Metrics
        self.violation_count = 0
        self.blocked_execution_count = 0
        self.alert_trigger_count = 0

    async def handle_violation(
        self, violation: ConstraintViolation, context: dict[str, Any] | None = None
    ) -> None:
        """
        Principal entry point for violation handling.
        Transitions the system to a REJECTED/HALTED state.
        """
        self.violation_count += 1
        self.blocked_execution_count += 1

        timestamp = datetime.utcnow().isoformat()
        violation_data = {
            "timestamp": timestamp,
            "constraint_id": violation.constraint_id,
            "message": violation.message,
            "context": context or {},
        }

        # 1. Structured Logging
        self.logger.log_event(
            module="ViolationHandler",
            action="handle_violation",
            status="HALT",
            message=violation.message,
            metadata={"constraint_id": violation.constraint_id},
            level="ERROR",
        )
        self._persist_violation(violation_data)

        # 2. Alert Generation
        await self._emit_alert(violation_data)
        self.alert_trigger_count += 1

        # 3. System-Wide Halt via FailFast
        # This ensures the orchestrator stops and safe state is preserved
        await self.failfast.handle_error(source="ViolationHandler", error=violation)

    def _persist_violation(self, data: dict[str, Any]) -> None:
        """Append violation to persistent log for audit."""
        try:
            logs = []
            if os.path.exists(self.log_path):
                with open(self.log_path) as f:
                    try:
                        logs = json.load(f)
                    except json.JSONDecodeError:
                        pass

            logs.append(data)
            with open(self.log_path, "w") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            # Critical logging failure
            print(f"CRITICAL_LOGGING_FAILURE | {e}")
            self.logger.log_event(
                module="ViolationHandler",
                action="_persist_violation",
                status="FAILED",
                message=str(e),
                level="CRITICAL",
            )

    async def _emit_alert(self, data: dict[str, Any]) -> None:
        """Propagate to institutional alerting channels (e.g., Slack, Email)."""
        alert_info = {
            "rule": f"VIOLATION_{data['constraint_id']}",
            "metric": "violation_count",
            "actual": 1.0,
            "threshold": 0.0,
            "severity": "CRITICAL",
            "action": "HALT_SYSTEM",
            "timestamp": data["timestamp"],
        }
        await alert_engine.trigger(alert_info)

    def get_metrics(self) -> dict[str, Any]:
        return {
            "violations": self.violation_count,
            "blocked": self.blocked_execution_count,
            "alerts": self.alert_trigger_count,
            "status": "ENFORCED",
        }


# Authoritative Instance
violation_handler = ViolationHandler()
