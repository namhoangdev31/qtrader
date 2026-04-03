"""Centralized Order Management System (OMS) with StateStore integration and strict FSM."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from qtrader.core.decimal_adapter import d, math_authority
from qtrader.core.events import (
    EventType,
    FillEvent,
    OrderEvent,
    SystemEvent,
    SystemPayload,
)
from qtrader.core.state_store import Order, Position, StateStore
from qtrader.oms.event_store import EventStore
from qtrader.oms.order_fsm import OrderFSM, OrderState

if TYPE_CHECKING:
    from qtrader.core.types import EventBusProtocol
    from qtrader.execution.brokers.base import BrokerAdapter

__all__ = ["UnifiedOMS"]

_LOG = logging.getLogger("qtrader.oms")


class UnifiedOMS:
    """
    Production-grade centralized Order Management System.
    Enforces a strict FSM and persists all transitions to the EventStore.
    State(t) = Σ Events[0 → t]
    """

    def __init__(self, state_store: StateStore, event_bus: EventBusProtocol) -> None:
        self.state_store = state_store
        self.event_bus = event_bus
        self.event_store = EventStore()
        self.fsm = OrderFSM()
        self.adapters: dict[str, BrokerAdapter] = {}
        self._log = _LOG

    def add_venue(self, name: str, adapter: BrokerAdapter) -> None:
        self.adapters[name] = adapter

    async def create_order(self, order_event: OrderEvent) -> None:
        """Create a new order and record its initial state."""
        # 1. State Store update (PENDING / NEW)
        order = Order(
            order_id=order_event.order_id,
            symbol=order_event.symbol,
            side=order_event.side,
            order_type=order_event.order_type,
            quantity=Decimal(str(order_event.quantity)),
            price=Decimal(str(order_event.price)) if order_event.price else None,
            timestamp=order_event.timestamp,
            status=OrderState.NEW.value,
        )
        await self.state_store.set_order(order)

        # 2. Event Recording
        created_event = SystemEvent(
            source="UnifiedOMS",
            trace_id=getattr(order_event, "trace_id", "unknown"),
            payload=SystemPayload(
                action="ORDER_CREATED",
                reason=f"New order: {order_event.symbol}",
                metadata={"order_id": order_event.order_id, "symbol": order_event.symbol},
            ),
        )
        await self.event_store.record_event(created_event)

        # 3. Bus Publication
        await self.event_bus.publish(created_event)
        self._log.info(f"OMS | Order Created: {order_event.order_id} [{order_event.symbol}]")

    async def on_ack(self, order_id: str) -> None:
        """Handle exchange acknowledgement (ACK)."""
        await self._transition(order_id, "ACK")

    async def on_reject(self, order_id: str, reason: str) -> None:
        """Handle order rejection from exchange."""
        await self._transition(order_id, "REJECT")
        rejected_event = SystemEvent(
            source="UnifiedOMS",
            trace_id="unknown",
            payload=SystemPayload(
                action="ORDER_REJECTED",
                reason=reason,
                metadata={"order_id": order_id},
            ),
        )
        await self.event_store.record_event(rejected_event)
        await self.event_bus.publish(rejected_event)
        self._log.error(f"OMS | Order Rejected: {order_id} - Reason: {reason}")

    async def cancel_order(self, order_id: str) -> None:
        """Handle order cancellation."""
        await self._transition(order_id, "CANCEL")
        self._log.info(f"OMS | Order Cancelled: {order_id}")

    async def on_fill(self, fill_event: FillEvent) -> None:
        """Handle order fill and update positions."""
        order_id = fill_event.order_id
        order = await self.state_store.get_order(order_id)
        if not order:
            self._log.warning(f"OMS | Fill received for untracked order: {order_id}")
            return

        # 1. Determine FSM event (PARTIAL vs COMPLETE)
        # Using Decimal for precision
        current_fill_total = await self._calculate_current_fill(order_id) + Decimal(
            str(fill_event.quantity)
        )
        is_complete = current_fill_total >= order.quantity
        fsm_event = "FILL_COMPLETE" if is_complete else "FILL_PARTIAL"

        # 2. Transition State
        await self._transition(order_id, fsm_event)

        # 3. Update Position centralized in StateStore
        await self._update_position(fill_event)

        # 4. Record and Publish
        filled_event = SystemEvent(
            source="UnifiedOMS",
            trace_id=getattr(fill_event, "trace_id", "unknown"),
            payload=SystemPayload(
                action="ORDER_FILLED",
                reason=f"Fill: {fill_event.payload.symbol}",
                metadata={
                    "order_id": order_id,
                    "symbol": fill_event.payload.symbol,
                    "quantity": str(fill_event.payload.quantity),
                    "price": str(fill_event.payload.price),
                    "side": fill_event.payload.side,
                    "remaining": str(order.quantity - current_fill_total),
                },
            ),
        )
        await self.event_store.record_event(filled_event)
        await self.event_bus.publish(filled_event)
        self._log.info(
            f"OMS | Order Fill: {order_id} ({fsm_event}) | Total Fill: {current_fill_total}/{order.quantity}"
        )

    async def _transition(self, order_id: str, event: str) -> None:
        """Centralized FSM transition logic."""
        order = await self.state_store.get_order(order_id)
        if not order:
            return

        current_state = order.status
        try:
            next_state = self.fsm.transition(current_state, event)
            await self.state_store.update_order(
                order_id, lambda o: setattr(o, "status", next_state)
            )
            self._log.debug(f"OMS | FSM Transition: {order_id} ({current_state} -> {next_state})")
        except ValueError as e:
            self._log.error(
                f"OMS | FSM Violation: {order_id} ({current_state} + {event} failed) - {e}"
            )

    async def _update_position(self, fill: FillEvent) -> None:
        """Update global system position in StateStore."""
        symbol = fill.symbol
        quantity = (
            Decimal(str(fill.quantity)) if fill.side == "BUY" else -Decimal(str(fill.quantity))
        )
        price = Decimal(str(fill.price))

        pos = await self.state_store.get_position(symbol)
        if pos:
            new_qty = pos.quantity + quantity
            # Update average cost (WAP)
            if new_qty != 0:
                if (pos.quantity > 0 and quantity > 0) or (pos.quantity < 0 and quantity < 0):
                    # Same side: update average price (WAP)
                    new_avg = ((pos.quantity * pos.average_price) + (quantity * price)) / new_qty
                else:
                    # Closing/Reducing position: average price remains same, realized P&L updated
                    new_avg = pos.average_price
                    realized = (
                        (price - pos.average_price)
                        * abs(quantity)
                        * (d(1) if pos.quantity > 0 else d(-1))
                    )
                    pos.realized_pnl += realized
            else:
                new_avg = d(0)
                realized = (
                    (price - pos.average_price)
                    * abs(quantity)
                    * (d(1) if pos.quantity > 0 else d(-1))
                )
                pos.realized_pnl += realized

            pos.quantity = new_qty
            pos.average_price = math_authority.to_price(abs(new_avg))
            pos.timestamp = datetime.utcnow()
            await self.state_store.set_position(pos)
        else:
            await self.state_store.set_position(
                Position(
                    symbol=symbol,
                    quantity=quantity,
                    average_price=price,
                    timestamp=datetime.utcnow(),
                )
            )

    async def _calculate_current_fill(self, order_id: str) -> Decimal:
        """Replay events for the order to calculate true current fill sum."""
        events = self.event_store.replay_order(order_id)
        total = Decimal("0")
        for ev in events:
            if ev.get("type") == "ORDER_FILLED":
                total += Decimal(str(ev.get("quantity", 0)))
        return total

    async def replay_state(self, order_id: str) -> str:
        """Reconstruct the latest state from event logs."""
        return self.event_store.get_latest_state(order_id)
