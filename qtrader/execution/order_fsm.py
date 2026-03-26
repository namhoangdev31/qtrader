"""Deterministic Order State Machine for tracking order lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.core.types import FillEvent


class OrderState(Enum):
    """Order states following the standard lifecycle."""

    NEW = "NEW"
    ACK = "ACK"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


@dataclass
class OrderFSM:
    """Deterministic Order State Machine with transition validation and history tracking."""

    order_id: str
    # Define valid transitions: from_state -> [list of valid to_states]
    _VALID_TRANSITIONS: dict[OrderState, list[OrderState]] = field(
        init=False,
        default_factory=lambda: {
            OrderState.NEW: [OrderState.ACK, OrderState.CANCELLED, OrderState.REJECTED],
            OrderState.ACK: [
                OrderState.PARTIALLY_FILLED,
                OrderState.FILLED,
                OrderState.CANCELLED,
                OrderState.REJECTED,
            ],
            OrderState.PARTIALLY_FILLED: [OrderState.FILLED, OrderState.CANCELLED],
            OrderState.FILLED: [],  # Terminal state
            OrderState.CANCELLED: [],  # Terminal state
            OrderState.REJECTED: [],  # Terminal state
        },
    )
    _state: OrderState = field(init=False, default=OrderState.NEW)
    _order_history: list[OrderState] = field(init=False, default_factory=list)
    _fill_history: list[FillEvent] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        """Initialize the order history with the starting state."""
        self._order_history = [self._state]

    @property
    def state(self) -> OrderState:
        """Get current order state."""
        return self._state

    @property
    def order_history(self) -> list[OrderState]:
        """Get copy of order state history."""
        return self._order_history.copy()

    @property
    def fill_history(self) -> list[FillEvent]:
        """Get copy of fill history."""
        return self._fill_history.copy()

    def transition(self, new_state: OrderState) -> None:
        """
        Transition to a new state with validation.

        Args:
            new_state: The target state to transition to

        Raises:
            InvalidTransitionError: If the transition is not valid
        """
        if new_state not in self._VALID_TRANSITIONS[self._state]:
            raise InvalidTransitionError(
                f"Invalid transition from {self._state.value} to {new_state.value} "
                f"for order {self.order_id}"
            )

        # Record the transition
        self._order_history.append(new_state)
        self._state = new_state

    def process_fill(self, fill: FillEvent) -> OrderState:
        """
        Process a fill event and record it.
        State transitions based on fills should be managed by the OMS/position manager
        which knows the actual order quantity vs filled quantity.

        Args:
            fill: The fill event to process

        Returns:
            Current order state (unchanged by fill processing alone)

        Raises:
            ValueError: If the fill doesn't match the order
        """
        # Validate fill matches order
        if fill.order_id != self.order_id:
            raise ValueError(f"Fill order_id {fill.order_id} does not match order {self.order_id}")

        # Record the fill
        self._fill_history.append(fill)

        # Note: Actual state transitions based on fill completion
        # (PARTIALLY_FILLED -> FILLED) should be handled by the OMS
        # when it determines the order is completely filled based on quantities.
        # This FSM simply records that a fill occurred.

        return self._state

    def is_terminal(self) -> bool:
        """Check if the order is in a terminal state."""
        return self._state in (OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED)

    def can_transition_to(self, state: OrderState) -> bool:
        """Check if transition to given state is valid from current state."""
        return state in self._VALID_TRANSITIONS[self._state]


def create_order_fsm(order_id: str) -> OrderFSM:
    """
    Factory function to create a new OrderFSM.

    Args:
        order_id: Unique identifier for the order

    Returns:
        New OrderFSM instance initialized to NEW state
    """
    return OrderFSM(order_id=order_id)
