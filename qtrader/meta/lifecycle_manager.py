from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any

_LOG = logging.getLogger("qtrader.meta.lifecycle_manager")


class LifecycleState(Enum):
    """
    Industrial Lifecycle States for autonomous strategy generation.

    Enforces the 'Valley of Death' progression logic to prevent premature alpha
    deployment and ensure rigorous out-of-sample verification.
    """

    RESEARCH = auto()  # Phase I: Symbolic Discovery & Discovery
    PAPER = auto()  # Phase II: Backtest-stable, Paper-Sandbox testing
    SHADOW = auto()  # Phase III: Live-mirror trading (zero capital)
    LIVE = auto()  # Phase IV: Active Capital Allocation
    KILLED = auto()  # Phase V: Decommissioned due to risk or obsolescence


class LifecycleEvent(Enum):
    """
    Strict Events triggering state transitions in the meta-system.
    """

    VALIDATED = auto()  # Syntactic and Static checks PASSED
    BACKTEST_PASS = auto()  # History replay benchmarks PASSED
    SHADOW_PASS = auto()  # Live mirroring benchmarks PASSED
    RISK_BREACH = auto()  # Hard limit breach or manual shutdown


class MetaLifecycleManager:
    """
    Deterministic Strategy Lifecycle Controller.

    Enforces a strict, non-skipping state machine RESEARCH -> PAPER -> SHADOW -> LIVE.
    Protects the system from 'Paper Alphas' by ensuring every strategy survives
    extensive live evaluation before graduating to actual execution.
    """

    def __init__(self) -> None:
        """
        Initialize the Lifecycle Manager and its transition registry.
        """
        self._strategy_registry: dict[str, LifecycleState] = {}

        # Allowed Sequential Transitions Mapping: current_state -> {event: next_state}
        self._transitions: dict[LifecycleState, dict[LifecycleEvent, LifecycleState]] = {
            LifecycleState.RESEARCH: {LifecycleEvent.VALIDATED: LifecycleState.PAPER},
            LifecycleState.PAPER: {LifecycleEvent.BACKTEST_PASS: LifecycleState.SHADOW},
            LifecycleState.SHADOW: {LifecycleEvent.SHADOW_PASS: LifecycleState.LIVE},
        }

    def transition(
        self, strategy_id: str, current_state: LifecycleState, event: LifecycleEvent
    ) -> LifecycleState:
        """
        Evaluate and apply a state transition to a candidate strategy.

        Args:
            strategy_id: Unique identifier for the strategy.
            current_state: The strategy's reported current lifecycle state.
            event: The industrial event triggering the transition evaluation.

        Returns:
            The resulting state (either updated or unchanged if transition was invalid).
        """
        # 1. Global Safety Gate: Any state can transition to KILLED on a RISK_BREACH
        if event == LifecycleEvent.RISK_BREACH:
            self._apply_transition(strategy_id, current_state, LifecycleState.KILLED, "RISK_BREACH")
            return LifecycleState.KILLED

        # 2. Sequential Progression Logic: Prevents state skipping (e.g. RESEARCH -> LIVE)
        allowed_map = self._transitions.get(current_state, {})
        new_state = allowed_map.get(event)

        if new_state:
            self._apply_transition(strategy_id, current_state, new_state, str(event.name))
            return new_state

        _LOG.warning(f"FORBIDDEN_TRANSITION | {strategy_id} | {current_state.name} + {event.name}")
        return current_state

    def _apply_transition(
        self,
        strategy_id: str,
        old_state: LifecycleState,
        new_state: LifecycleState,
        reason: str,
    ) -> None:
        """
        Commit the state update to the registry and emit audit logs.
        """
        self._strategy_registry[strategy_id] = new_state
        _LOG.info(
            f"[TRANSITION] {strategy_id} | {old_state.name} -> {new_state.name} | Reason: {reason}"
        )

    def get_observability_report(self) -> dict[str, Any]:
        """
        Generate a lifecycle distribution report for research governance.
        """
        dist = {state.name: 0 for state in LifecycleState}
        for state in self._strategy_registry.values():
            dist[state.name] += 1

        return {
            "status": "TRANSITION",
            "state_distribution": dist,
            "total_tracked": len(self._strategy_registry),
        }
