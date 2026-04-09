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
from qtrader_core import OrderFSM as RustOrderFSM, OrderStatus

logger = logging.getLogger(__name__)


class OrderState(Enum):
    NEW = "NEW"
    ACK = "ACK"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


# Mapping Python OrderState to Rust OrderStatus
STATE_TO_STATUS = {
    OrderState.NEW.value: OrderStatus.New,
    OrderState.ACK.value: OrderStatus.Ack,
    OrderState.PARTIAL.value: OrderStatus.Partial,
    OrderState.FILLED.value: OrderStatus.Filled,
    OrderState.CLOSED.value: OrderStatus.Closed,
    OrderState.REJECTED.value: OrderStatus.Rejected,
}

def get_state_from_status(status: OrderStatus) -> str:
    """Helper to find OrderState value from Rust OrderStatus variant."""
    # 1. Try direct comparison (fastest)
    for state_val, rust_status in STATE_TO_STATUS.items():
        if rust_status == status:
            return state_val
            
    # 2. Fallback to string-based mapping if equality fails (C-extension quirk)
    status_repr = str(status)
    if "New" in status_repr: return OrderState.NEW.value
    if "Ack" in status_repr: return OrderState.ACK.value
    if "Partial" in status_repr: return OrderState.PARTIAL.value
    if "Filled" in status_repr: return OrderState.FILLED.value
    if "Closed" in status_repr: return OrderState.CLOSED.value
    if "Rejected" in status_repr: return OrderState.REJECTED.value

    raise ValueError(f"Unknown status type: {type(status)} | value: {status}")


class OrderFSM:
    """High-performance Order FSM using Rust Core."""

    def __init__(self, pending_timeout_s: float = 30.0) -> None:
        self.pending_timeout_s = pending_timeout_s
        self._rust_fsm = RustOrderFSM(pending_timeout_s)
        self._state_timestamps: dict[str, float] = {}

    def transition(self, current_state: str, event: str) -> str:
        status = STATE_TO_STATUS.get(current_state)
        if status is None:
            raise ValueError(f"Unknown state: {current_state}")

        try:
            new_status = self._rust_fsm.transition(status, event)
            return get_state_from_status(new_status)
        except Exception as e:
            raise ValueError(str(e))

    def record_state_entry(self, order_id: str, state: str) -> None:
        self._state_timestamps[order_id] = time.time()
        if state in ("FILLED", "CLOSED", "REJECTED"):
            self._state_timestamps.pop(order_id, None)

    def check_timeout(self, order_id: str) -> bool:
        entry_time = self._state_timestamps.get(order_id)
        if entry_time is None:
            return False

        elapsed = time.time() - entry_time
        if elapsed > self.pending_timeout_s:
            logger.warning(f"OrderFSM | TIMEOUT | Order {order_id} elapsed {elapsed:.1f}s")
            return True
        return False

    def get_pending_orders(self, order_ids: list[str]) -> list[str]:
        return [oid for oid in order_ids if oid in self._state_timestamps]

    def cleanup(self, order_id: str) -> None:
        self._state_timestamps.pop(order_id, None)
