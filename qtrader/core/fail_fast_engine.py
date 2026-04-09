from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.errors import BaseError, CriticalError, RecoverableError, classify_error

if TYPE_CHECKING:
    from qtrader.core.global_orchestrator import GlobalOrchestrator


@dataclass
class EscalationState:
    count: int = 0
    first_occurrence: float = field(default_factory=time.time)


class FailFastEngine:
    def __init__(
        self,
        global_orchestrator: GlobalOrchestrator | None = None,
        max_retries: int = 3,
        escalation_window_sec: int = 60,
    ) -> None:
        self._orchestrator = global_orchestrator
        self._max_retries = max_retries
        self._escalation_window = escalation_window_sec
        self._escalation_map: dict[str, EscalationState] = {}
        self.trigger_count: int = 0
        self.halt_count: int = 0

    async def handle_error(self, source: str, error: Exception) -> None:
        self.trigger_count += 1
        classified = classify_error(error)
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
        if not isinstance(error, RecoverableError):
            return error
        now = time.time()
        state = self._escalation_map.get(source, EscalationState())
        if now - state.first_occurrence > self._escalation_window:
            state = EscalationState(first_occurrence=now)
        state.count += 1
        self._escalation_map[source] = state
        if state.count > self._max_retries:
            logger.error(f"[FAIL-FAST] Escalating {source}: Too many retries ({state.count})")
            return CriticalError(
                message=f"Escalated Failure: {source} exceeded retry limit of {self._max_retries}",
                metadata={"original_error": str(error)},
            )
        return error

    async def _halt_system(self, source: str, reason: str) -> None:
        self.halt_count += 1
        logger.critical(f"[FAIL-FAST] DETERMINISTIC HALT TRIGGERED by {source}")
        if self._orchestrator:
            await self._orchestrator.engage_global_kill_switch(reason=f"Fail-Fast Halt: {reason}")
        else:
            logger.error(
                "[FAIL-FAST] ORCHESTRATOR MISSING - Performing process-level emergency exit."
            )

            sys.exit(1)

    async def _isolate_module(self, source: str, reason: str) -> None:
        logger.error(f"[FAIL-FAST] ISOLATION PROTOCOL ENGAGED for {source}")

    async def _trigger_retry(self, source: str, reason: str) -> None:
        logger.info(f"[FAIL-FAST] RETRY PROTOCOL ENGAGED for {source}")

    def get_status(self) -> dict[str, Any]:
        return {
            "status": "ENFORCED",
            "trigger_count": self.trigger_count,
            "halt_count": self.halt_count,
            "escalation_entries": len(self._escalation_map),
        }
