from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from loguru import logger


class LatencyViolation(Exception):
    """Exception raised when an execution stage exceeds its defined latency budget."""
    pass


class LatencyMonitor:
    """
    Sovereign Authority for Latency Governance.
    Instruments the CriticalPath (Market -> Alpha -> Order).
    Enforces the institutional 100ms execution budget.
    """

    _instance: Optional[LatencyMonitor] = None

    def __init__(self, budget_policy: dict[str, Any]) -> None:
        self.policy = budget_policy.get("budgets", {})
        self.rules = budget_policy.get("rules", {})
        self._timers: Dict[str, float] = {}
        self._accumulated_ms: float = 0.0

    @classmethod
    def get_instance(cls, budget_policy: Optional[dict[str, Any]] = None) -> LatencyMonitor:
        if cls._instance is None:
             if budget_policy is None:
                  # Prototype fallback
                  budget_policy = {"budgets": {"total_end_to_end": 100.0}}
             cls._instance = LatencyMonitor(budget_policy)
        return cls._instance

    def start_stage(self, stage: str) -> None:
        """Inject a high-resolution timestamp at stage entry."""
        self._timers[stage] = time.perf_counter_ns()

    def end_stage(self, stage: str) -> float:
        """
        Measure stage duration, compare against budget, and update accumulated transit.
        Returns: duration in milliseconds.
        """
        if stage not in self._timers:
            logger.warning(f"[LATENCY] Stage '{stage}' ended without start_stage call.")
            return 0.0
            
        end_time = time.perf_counter_ns()
        duration_ns = end_time - self._timers.pop(stage)
        duration_ms = duration_ns / 1_000_000.0
        
        self._accumulated_ms += duration_ms
        
        limit = self.policy.get(stage)
        if limit and duration_ms > limit:
             self._record_violation(stage, duration_ms, limit)
             
        # Global budget check
        total_limit = self.policy.get("total_end_to_end", 100.0)
        if self._accumulated_ms > total_limit:
             self._record_violation("total_pipeline", self._accumulated_ms, total_limit)
             
        return duration_ms

    def reset_pipeline(self) -> None:
        """Reset accumulated latency for a new market event lifecycle."""
        self._timers.clear()
        self._accumulated_ms = 0.0

    def _record_violation(self, stage: str, actual: float, limit: float) -> None:
        """Log the breach and trigger fail-fast halt if configured."""
        msg = (
            f"Latency Budget Breach: Stage='{stage}' took {actual:.3f}ms (Limit={limit}ms). "
            f"THIS VIOLATES THE INSTITUTIONAL 100ms SLA."
        )
        logger.error(f"[FATAL] {msg}")
        
        if self.rules.get("fail_on_breach", True):
            raise LatencyViolation(msg)

    @property
    def total_latency_ms(self) -> float:
        return self._accumulated_ms


# Initialization Example (To be integrated into system orchestrator)
prototype_policy = {
    "budgets": {
        "market_data_ingestion": 5.0,
        "alpha_computation": 20.0,
        "order_routing": 15.0,
        "total_end_to_end": 100.0
    },
    "rules": {
        "fail_on_breach": True
    }
}
latency_enforcer = LatencyMonitor.get_instance(prototype_policy)
