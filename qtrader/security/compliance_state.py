from __future__ import annotations
import logging
import time
from enum import Enum
from typing import Any, Final

_LOG = logging.getLogger("qtrader.security.compliance_state")


class SystemState(Enum):
    NORMAL = 1
    WARNING = 2
    BREACH = 3
    RESTRICTED = 4
    HALTED = 5


class ComplianceStateEnforcer:
    def __init__(self, max_var: float = 0.05, max_dd: float = 0.15) -> None:
        self._max_var: Final[float] = max_var
        self._max_dd: Final[float] = max_dd
        self._current_state = SystemState.NORMAL
        self._last_transition = time.time()
        self._stats = {"transitions": 0, "halt_events": 0}

    @property
    def current_state(self) -> SystemState:
        return self._current_state

    def update_state(self, var_score: float, current_dd: float) -> SystemState:
        target_state = SystemState.NORMAL
        if var_score > self._max_var:
            target_state = SystemState.HALTED
        elif current_dd > self._max_dd:
            target_state = SystemState.RESTRICTED
        elif current_dd > 0.8 * self._max_dd:
            target_state = SystemState.BREACH
        elif current_dd > 0.5 * self._max_dd:
            target_state = SystemState.WARNING
        if target_state.value > self._current_state.value:
            self._execute_transition(target_state)
        return self._current_state

    def _execute_transition(self, new_state: SystemState) -> None:
        old_state = self._current_state
        self._current_state = new_state
        self._last_transition = time.time()
        self._stats["transitions"] += 1
        if new_state == SystemState.HALTED:
            self._stats["halt_events"] += 1
        _LOG.warning(f"[STATE_UPDATE] TRANSITION | {old_state.name} -> {new_state.name}")

    def request_recovery(self, target_state: SystemState, override_id: str) -> bool:
        if "OVR_" not in override_id:
            _LOG.error(f"[STATE_UPDATE] RECOVERY_DENY | Invalid Override Token: {override_id}")
            return False
        if target_state.value >= self._current_state.value:
            _LOG.warning("[STATE_UPDATE] RECOVERY_ERROR | No restoration needed.")
            return False
        old_state = self._current_state
        self._current_state = target_state
        self._last_transition = time.time()
        _LOG.info(
            f"[STATE_UPDATE] RECOVERY_GRANTED | {old_state.name} -> {target_state.name} | Token: {override_id}"
        )
        return True

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "REPORT",
            "current_state": self._current_state.name,
            "state_age_s": round(time.time() - self._last_transition, 2),
            "transition_count": self._stats["transitions"],
            "halt_events": self._stats["halt_events"],
        }
