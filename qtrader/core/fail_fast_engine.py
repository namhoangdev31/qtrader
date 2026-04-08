from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.errors import (
    BaseError,
    CriticalError,
    RecoverableError,
    classify_error,
)

if TYPE_CHECKING:
    from qtrader.core.global_orchestrator import GlobalOrchestrator


@dataclass
class EscalationState:
    """Tracks error frequency for escalation logic."""
    count: int = 0
    first_occurrence: float = field(default_factory=time.time)


class FailFastEngine:
    """
    Risk Enforcement Engine.
    Ensures that system failures immediately trigger a deterministic response.
    """

    def __init__(
        self, 
        global_orchestrator: GlobalOrchestrator | None = None,
        max_retries: int = 3,
        escalation_window_sec: int = 60
    ) -> None:
        self._orchestrator = global_orchestrator
        self._max_retries = max_retries
        self._escalation_window = escalation_window_sec
        self._escalation_map: dict[str, EscalationState] = {}
        
        # Metrics
        self.trigger_count: int = 0
        self.halt_count: int = 0

    async def handle_error(self, source: str, error: Exception) -> None:
        """
        Principal entry point for failure response.
        Maps the exception to the taxonomy and applies the enforcement policy.
        """
        self.trigger_count += 1
        classified = classify_error(error)
        
        # 1. State-aware Escalation
        final_error = self._apply_escalation(source, classified)
        
        severity = getattr(final_error, "severity", 3)
        message = str(final_error)

        logger.warning(f"[FAIL-FAST] Intercepted {source} | Severity={severity} | {message}")

        if severity >= 3:
            await self._halt_system(source, message)
        elif severity == 2:
            await self._isolate_module(source, message)
        else:
            await self._trigger_retry(source, message)

    def _apply_escalation(self, source: str, error: BaseError) -> BaseError:
        """
        Escalates RecoverableError if it occurs too frequently.
        """
        if not isinstance(error, RecoverableError):
            return error

        now = time.time()
        state = self._escalation_map.get(source, EscalationState())
        
        # Reset window if expired
        if now - state.first_occurrence > self._escalation_window:
            state = EscalationState(first_occurrence=now)

        state.count += 1
        self._escalation_map[source] = state

        if state.count > self._max_retries:
            logger.error(f"[FAIL-FAST] Escalating {source}: Too many retries ({state.count})")
            return CriticalError(
                message=f"Escalated Failure: {source} exceeded retry limit of {self._max_retries}",
                metadata={"original_error": str(error)}
            )
        
        return error

    async def _halt_system(self, source: str, reason: str) -> None:
        """Triggers the Global Kill Switch via the Orchestrator."""
        self.halt_count += 1
        logger.critical(f"[FAIL-FAST] DETERMINISTIC HALT TRIGGERED by {source}")
        
        if self._orchestrator:
            await self._orchestrator.engage_global_kill_switch(reason=f"Fail-Fast Halt: {reason}")
        else:
            logger.error("[FAIL-FAST] ORCHESTRATOR MISSING - Performing process-level emergency exit.")
            # Fatal fallback if orchestrator is detached
            import sys
            sys.exit(1)

    async def _isolate_module(self, source: str, reason: str) -> None:
        """Instructs the system to isolate the failing component."""
        logger.error(f"[FAIL-FAST] ISOLATION PROTOCOL ENGAGED for {source}")
        # In this architecture, isolation is currently handled by logging and 
        # stopping specific strategy loops if the orchestrator supports it.
        # Future enhancement: orchestrator.stop_worker(source)

    async def _trigger_retry(self, source: str, reason: str) -> None:
        """Triggers a non-blocking retry alert."""
        logger.info(f"[FAIL-FAST] RETRY PROTOCOL ENGAGED for {source}")
        # Retries are predominantly handled by the source module's own logic 
        # (e.g. backoff decorators), but the engine tracks the attempt for escalation.

    def get_status(self) -> dict[str, Any]:
        """Returns the enforcement status for observability."""
        return {
            "status": "ENFORCED",
            "trigger_count": self.trigger_count,
            "halt_count": self.halt_count,
            "escalation_entries": len(self._escalation_map)
        }
