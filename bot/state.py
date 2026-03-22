"""Bot state machine and allowed transitions."""

from __future__ import annotations

import logging
from enum import Enum

__all__ = ["BotState", "StateMachine"]

_LOG = logging.getLogger("bot.state")


class BotState(str, Enum):
    """Bot lifecycle states."""

    INITIALIZING = "initializing"
    WARMING_UP = "warming_up"
    TRADING = "trading"
    RISK_HALTED = "risk_halted"
    RETRAINING = "retraining"
    SHUTTING_DOWN = "shutting_down"
    EMERGENCY = "emergency"


class StateMachine:
    """State machine for bot lifecycle with enforced transitions."""

    ALLOWED_TRANSITIONS: dict[BotState, list[BotState]] = {
        BotState.INITIALIZING: [BotState.WARMING_UP],
        BotState.WARMING_UP: [BotState.TRADING, BotState.EMERGENCY],
        BotState.TRADING: [
            BotState.RISK_HALTED,
            BotState.RETRAINING,
            BotState.SHUTTING_DOWN,
            BotState.EMERGENCY,
        ],
        BotState.RISK_HALTED: [BotState.TRADING, BotState.SHUTTING_DOWN, BotState.EMERGENCY],
        BotState.RETRAINING: [BotState.TRADING, BotState.EMERGENCY],
        BotState.SHUTTING_DOWN: [],
        BotState.EMERGENCY: [],
    }

    def __init__(self) -> None:
        self._state = BotState.INITIALIZING
        self._reason = ""

    @property
    def state(self) -> BotState:
        """Current bot state."""
        return self._state

    def transition(self, new_state: BotState, reason: str) -> None:
        """Transition to a new state if allowed.

        Args:
            new_state: Target state.
            reason: Human-readable reason for the transition.

        Raises:
            ValueError: If the transition is not allowed.
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self._state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition from {self._state.value} to {new_state.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        _LOG.info("Bot state: %s -> %s (%s)", self._state.value, new_state.value, reason)
        self._state = new_state
        self._reason = reason

    def can_trade(self) -> bool:
        """Return True only when state is TRADING."""
        return self._state == BotState.TRADING


"""
# Pytest-style examples:
def test_state_machine_can_trade() -> None:
    sm = StateMachine()
    sm.transition(BotState.WARMING_UP, "warmup")
    assert not sm.can_trade()
    sm.transition(BotState.TRADING, "ready")
    assert sm.can_trade()

def test_state_machine_invalid_transition() -> None:
    sm = StateMachine()
    with pytest.raises(ValueError):
        sm.transition(BotState.TRADING, "skip")
"""
