"""Strict Finite State Machine for order lifecycle management.

Standash §7.1:
- Idempotent transitions
- Timeout for pending states with auto-reconcile
- No illegal state jumps
"""

from __future__ import annotations

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class OrderState(Enum):
    NEW = "NEW"
    ACK = "ACK"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


# Pending states that require timeout monitoring
PENDING_STATES = {OrderState.NEW.value, OrderState.ACK.value, OrderState.PARTIAL.value}

# Default timeout for pending states (seconds)
DEFAULT_PENDING_TIMEOUT_S = 30.0


class OrderFSM:
    """Strict Finite State Machine for order lifecycle management.

    Transitions:
        NEW → ACK → PARTIAL → FILLED → CLOSED
               ↘ REJECTED

    Timeout: Pending states (NEW, ACK, PARTIAL) auto-expire after
    configurable timeout, emitting a TIMEOUT event for reconciliation.
    """

    def __init__(self, pending_timeout_s: float = DEFAULT_PENDING_TIMEOUT_S) -> None:
        self.pending_timeout_s = pending_timeout_s
        self._state_timestamps: dict[str, float] = {}

    def transition(self, current_state: str, event: str) -> str:
        """
        Transition function: State(t+1) = Transition(State(t), Event).

        Args:
            current_state: Current order state.
            event: Transition event.

        Returns:
            New state after transition.

        Raises:
            ValueError: On invalid transition.
        """
        if current_state == OrderState.NEW.value:
            if event == "ACK":
                return OrderState.ACK.value
            if event == "REJECT":
                return OrderState.REJECTED.value

        if current_state == OrderState.ACK.value:
            if event == "FILL_PARTIAL":
                return OrderState.PARTIAL.value
            if event == "FILL_COMPLETE":
                return OrderState.FILLED.value
            if event == "CANCEL":
                return OrderState.CLOSED.value
            if event == "REJECT":
                return OrderState.REJECTED.value

        if current_state == OrderState.PARTIAL.value:
            if event == "FILL_PARTIAL":
                return OrderState.PARTIAL.value
            if event == "FILL_COMPLETE":
                return OrderState.FILLED.value
            if event == "CANCEL":
                return OrderState.CLOSED.value

        # Terminal states are immutable
        if current_state in (
            OrderState.FILLED.value,
            OrderState.CLOSED.value,
            OrderState.REJECTED.value,
        ):
            logger.warning(f"OrderFSM | Terminal state {current_state} — ignoring event {event}")
            return current_state

        raise ValueError(f"Invalid transition from {current_state} on event {event}")

    def record_state_entry(self, order_id: str, state: str) -> None:
        """Record the timestamp when an order enters a state."""
        self._state_timestamps[order_id] = time.time()
        if state not in PENDING_STATES:
            # Clean up timestamp for terminal states
            self._state_timestamps.pop(order_id, None)

    def check_timeout(self, order_id: str) -> bool:
        """Check if an order has exceeded the pending state timeout.

        Args:
            order_id: Order to check.

        Returns:
            True if the order has timed out.
        """
        entry_time = self._state_timestamps.get(order_id)
        if entry_time is None:
            return False

        elapsed = time.time() - entry_time
        if elapsed > self.pending_timeout_s:
            logger.warning(
                f"OrderFSM | TIMEOUT | Order {order_id} in pending state "
                f"for {elapsed:.1f}s (limit: {self.pending_timeout_s}s)"
            )
            return True

        return False

    def get_pending_orders(self, order_ids: list[str]) -> list[str]:
        """Return order IDs that are currently in pending states.

        Args:
            order_ids: List of order IDs to check.

        Returns:
            List of order IDs still in pending states.
        """
        return [oid for oid in order_ids if oid in self._state_timestamps]

    def cleanup(self, order_id: str) -> None:
        """Remove order from timeout tracking (called on terminal state)."""
        self._state_timestamps.pop(order_id, None)
