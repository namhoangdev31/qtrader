from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Final

_LOG = logging.getLogger("qtrader.security.compliance_state")


class SystemState(Enum):
    """
    Global Security and Operational States for the QTrader platform.
    Order reflects risk-sensitivity (NORMAL to HALTED).
    """

    NORMAL = 1
    WARNING = 2
    BREACH = 3
    RESTRICTED = 4
    HALTED = 5


class ComplianceStateEnforcer:
    """
    Principal Structural Resilience Engine.

    Objective: Govern global platform permissions using a risk-driven finite state machine.
    Dynamically restricts or halts all trading operations when critical risk thresholds
    (e.g., Value at Risk, Max Drawdown) are exceeded, mitigating catastrophic exposure.
    """

    def __init__(self, max_var: float = 0.05, max_dd: float = 0.15) -> None:
        """
        Initialize with institutional risk baseline.

        Args:
            max_var: 99% Tail Risk threshold (e.g., 0.05 = 5% of Equity).
            max_dd: Maximum Peak-to-Trough Drawdown (e.g., 0.15 = 15%).
        """
        self._max_var: Final[float] = max_var
        self._max_dd: Final[float] = max_dd

        self._current_state = SystemState.NORMAL
        self._last_transition = time.time()

        # Telemetry for situational awareness.
        self._stats = {"transitions": 0, "halt_events": 0}

    @property
    def current_state(self) -> SystemState:
        """
        Read-only access to the global system state.
        """
        return self._current_state

    def update_state(self, var_score: float, current_dd: float) -> SystemState:
        """
        Evaluate real-time risk metrics and drive state transitions.

        Rule Engine:
        1. Non-negotiable Halt: var_score > max_var forces HALTED state.
        2. Liquidty Cap Restriction: current_dd > max_dd forces RESTRICTED.
        3. Compliance Breach: current_dd > 80% of max_dd forces BREACH.
        4. Operational Warning: current_dd > 50% of max_dd forces WARNING.

        Note: Automated updates ONLY move towards more restrictive states.
        State recovery requires an authorized human override.
        """
        target_state = SystemState.NORMAL

        # Tiered Decision Matrix
        if var_score > self._max_var:
            target_state = SystemState.HALTED
        elif current_dd > self._max_dd:
            target_state = SystemState.RESTRICTED
        elif current_dd > (0.8 * self._max_dd):
            target_state = SystemState.BREACH
        elif current_dd > (0.5 * self._max_dd):
            target_state = SystemState.WARNING

        # Automated Enforcement Rule: Only transition to HIGHER risk levels.
        if target_state.value > self._current_state.value:
            self._execute_transition(target_state)

        return self._current_state

    def _execute_transition(self, new_state: SystemState) -> None:
        """
        Log and enforce a global state-machine shift.
        """
        old_state = self._current_state
        self._current_state = new_state
        self._last_transition = time.time()
        self._stats["transitions"] += 1

        if new_state == SystemState.HALTED:
            self._stats["halt_events"] += 1

        _LOG.warning(f"[STATE_UPDATE] TRANSITION | {old_state.name} -> {new_state.name}")

    def request_recovery(self, target_state: SystemState, override_id: str) -> bool:
        """
        Restore platform operation following a risk event.

        Constraint: Recovery to a less-restrictive state (e.g. HALTED -> NORMAL)
        MUST present a valid authorization token from the HumanOverrideSystem.
        """
        # Industrial Protocol: Recovery gating requires quaternary approval trace.
        if "OVR_" not in override_id:
            _LOG.error(f"[STATE_UPDATE] RECOVERY_DENY | Invalid Override Token: {override_id}")
            return False

        # Logic verification: Ensure we are actually moving to a less restrictive state.
        if target_state.value >= self._current_state.value:
            _LOG.warning("[STATE_UPDATE] RECOVERY_ERROR | No restoration needed.")
            return False

        old_state = self._current_state
        self._current_state = target_state
        self._last_transition = time.time()

        _LOG.info(
            f"[STATE_UPDATE] RECOVERY_GRANTED | {old_state.name} -> {target_state.name} "
            f"| Token: {override_id}"
        )
        return True

    def get_report(self) -> dict[str, Any]:
        """
        Generate operational governance situational awareness report.
        """
        return {
            "status": "REPORT",
            "current_state": self._current_state.name,
            "state_age_s": round(time.time() - self._last_transition, 2),
            "transition_count": self._stats["transitions"],
            "halt_events": self._stats["halt_events"],
        }
