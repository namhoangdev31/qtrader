from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

from qtrader.core.events import (
    FSMErrorEvent,
    FSMErrorPayload,
    StrategyStateEvent,
    StrategyStatePayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus


class StrategyFSM:
    """
    Finite State Machine for Strategy Lifecycle Governance.

    Enforces deterministic state transitions for all active strategies:
    INIT -> SANDBOX -> APPROVED -> ACTIVE <-> PAUSED
    ACTIVE -> KILLED
    """

    # Valid Lifecycle States
    INIT = "INIT"
    SANDBOX = "SANDBOX"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    KILLED = "KILLED"

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize FSM with the global event bus.
        """
        self._event_bus = event_bus
        self._strategy_registry: dict[str, str] = {}

        # User-defined strict transition mapping: state -> [valid_next_states]
        self._allowed_transitions: dict[str, set[str]] = {
            self.INIT: {self.SANDBOX},
            self.SANDBOX: {self.APPROVED},
            self.APPROVED: {self.ACTIVE},
            self.ACTIVE: {self.PAUSED, self.KILLED},
            self.PAUSED: {self.ACTIVE, self.KILLED},
            self.KILLED: set(),
        }

        # System-level trace ID for governance broadcasts
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def transition(
        self, strategy_id: str, new_state: str, reason: str = "GOVERNANCE_COMMAND"
    ) -> bool:
        """
        Apply a state transition to a strategy after validation.
        """
        try:
            current_state = self._strategy_registry.get(strategy_id, self.INIT)

            # Validation: Block invalid transitions as per governance protocol
            if new_state not in self._allowed_transitions.get(current_state, set()):
                await self._emit_fsm_error(
                    str(strategy_id),
                    "INVALID_TRANSITION",
                    f"Forbidden transition from {current_state} to {new_state}",
                )
                return False

            # Success: Update state and broadcast lifecycle event
            self._strategy_registry[strategy_id] = new_state

            event = StrategyStateEvent(
                trace_id=self._system_trace,
                source="StrategyFSM",
                payload=StrategyStatePayload(
                    strategy_id=strategy_id,
                    old_state=current_state,
                    new_state=new_state,
                    reason=reason,
                    metadata={"timestamp_ms": int(time.time() * 1000)},
                ),
            )

            await self._event_bus.publish(event)
            logger.info(f"STRATEGY_LIFECYCLE | {strategy_id} | {current_state} -> {new_state}")
            return True

        except Exception as e:
            logger.error(f"FSM_FAILURE | {strategy_id} | {e!s}")
            # Ensure we don't crash the error emitter itself
            try:
                await self._emit_fsm_error(str(strategy_id), "SYSTEM_FAILURE", str(e))
            except Exception as nested_e:
                logger.error(f"FSM_CRITICAL_RECOVERY_FAILURE | {nested_e!s}")
            return False

    def get_state(self, strategy_id: str) -> str:
        """Retrieve the current state of a strategy."""
        return self._strategy_registry.get(strategy_id, self.INIT)

    def is_active(self, strategy_id: str) -> bool:
        """Check if a strategy is currently in the ACTIVE state."""
        return self._strategy_registry.get(strategy_id, self.INIT) == self.ACTIVE

    async def _emit_fsm_error(self, entity_id: str, err_type: str, details: str) -> None:
        """Emit a FSM_ERROR event to the global bus."""
        error_event = FSMErrorEvent(
            trace_id=self._system_trace,
            source="StrategyFSM",
            payload=FSMErrorPayload(entity_id=entity_id, error_type=err_type, details=details),
        )
        await self._event_bus.publish(error_event)
