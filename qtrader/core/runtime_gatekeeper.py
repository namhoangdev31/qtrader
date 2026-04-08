from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.enforcement_engine import enforcement_engine
from qtrader.core.exceptions import SystemHalt

if TYPE_CHECKING:
    from qtrader.core.events import BaseEvent


class RuntimeGatekeeper:
    """
    Sovereign Runtime Gatekeeper (Phase -1.5 G7 P2).
    Enforces execution gates during runtime and halts the system upon violations.
    """

    def __init__(
        self,
        halt_log_path: str = "qtrader/logs/halt_log.json",
        monitoring_map_path: str = "qtrader/audit/runtime_monitoring_map.json"
    ) -> None:
        self.halt_log_path = halt_log_path
        self.monitoring_map_path = monitoring_map_path
        self.halt_count = 0
        self.violations_detected = 0
        
        # Initialize monitoring map structure
        self._monitoring_data = {
            "status": "ACTIVE_PROTECTION",
            "halt_count": 0,
            "runtime_violations": 0,
            "stage_metrics": {}
        }
        self._ensure_paths()
        self._save_monitoring_map()

    def _ensure_paths(self) -> None:
        """Ensure directories for logs and audit exist."""
        os.makedirs(os.path.dirname(self.halt_log_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.monitoring_map_path), exist_ok=True)

    async def check(self, context: dict[str, Any]) -> None:
        """
        Monitor runtime conditions for a specific execution context.
        Raises SystemHalt if EnforcementEngine detects a violation.
        """
        stage = context.get("stage", "unknown")
        try:
            await enforcement_engine.validate_pre_execution(context)
            self._update_stage_metrics(stage, success=True)
        except Exception as e:
            self.violations_detected += 1
            self._update_stage_metrics(stage, success=False)
            await self.halt(reason=str(e), context=context)

    async def check_event(self, event: BaseEvent) -> None:
        """
        Monitor runtime conditions for a specific event.
        Raises SystemHalt if EnforcementEngine detects a violation.
        """
        stage = f"event_{event.event_type.name if hasattr(event, 'event_type') else 'unknown'}"
        try:
            await enforcement_engine.validate_event(event)
            self._update_stage_metrics(stage, success=True)
        except Exception as e:
            self.violations_detected += 1
            self._update_stage_metrics(stage, success=False)
            await self.halt(reason=str(e), context={"event": str(event)})

    async def halt(self, reason: str, context: dict[str, Any] | None = None) -> None:
        """
        Emergency halt protocol.
        Persists forensic data and raises terminal SystemHalt exception.
        """
        self.halt_count += 1
        timestamp = datetime.now(timezone.utc).isoformat()
        
        halt_entry = {
            "timestamp": timestamp,
            "reason": reason,
            "context": context or {}
        }
        
        logger.critical(f"RUNTIME_GATEKEEPER_HALT | {reason}")
        self._persist_halt(halt_entry)
        
        # Update and persist monitoring map before crashing
        self._monitoring_data["halt_count"] = self.halt_count
        self._monitoring_data["runtime_violations"] = self.violations_detected
        self._save_monitoring_map()
        
        raise SystemHalt(message=reason, metadata=context)

    def _persist_halt(self, entry: dict[str, Any]) -> None:
        """Append halt entry to persistent log."""
        try:
            logs = []
            if os.path.exists(self.halt_log_path):
                with open(self.halt_log_path) as f:
                    try:
                        logs = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            logs.append(entry)
            with open(self.halt_log_path, "w") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            logger.error(f"HALT_LOGGING_FAILURE | {e}")

    def _update_stage_metrics(self, stage: str, success: bool) -> None:
        """Update metrics for a specific pipeline stage."""
        if stage not in self._monitoring_data["stage_metrics"]:
            self._monitoring_data["stage_metrics"][stage] = {"checks": 0, "violations": 0}
            
        self._monitoring_data["stage_metrics"][stage]["checks"] += 1
        if not success:
            self._monitoring_data["stage_metrics"][stage]["violations"] += 1
        
        # Save monitoring map for real-time observability
        self._save_monitoring_map()

    def _save_monitoring_map(self) -> None:
        """Persist real-time monitoring state."""
        try:
            with open(self.monitoring_map_path, "w") as f:
                json.dump(self._monitoring_data, f, indent=2)
        except Exception as e:
            logger.error(f"MONITORING_MAP_FAILURE | {e}")

    def get_report(self) -> dict[str, Any]:
        """Returns report in the standardized format."""
        return {
            "halts": self.halt_count,
            "violations": self.violations_detected,
            "status": self._monitoring_data["status"]
        }


# Authoritative Global Instance
runtime_gatekeeper = RuntimeGatekeeper()
