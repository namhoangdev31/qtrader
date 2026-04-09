"""Centralized Order Management System (OMS) with StateStore integration and strict FSM."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from qtrader_core import Order as RustOrder
from qtrader_core import OrderType as RustOrderType
from qtrader_core import Side as RustSide
from qtrader_core import UnifiedOMS as RustUnifiedOMS

from qtrader.core.events import (
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
    Delegates all execution and position logic to the Rust core.
    """

    def __init__(
        self,
        state_store: StateStore,
        event_bus: EventBusProtocol,
        initial_capital: float = 1_000_000.0,
    ) -> None:
        self.state_store = state_store
        self.event_bus = event_bus
        self.event_store = EventStore()
        self.fsm = OrderFSM()
        self._rust_oms = RustUnifiedOMS(initial_capital, self.fsm.pending_timeout_s)
        self.adapters: dict[str, BrokerAdapter] = {}
        self._log = _LOG

    def add_venue(self, name: str, adapter: BrokerAdapter) -> None:
        self.adapters[name] = adapter

    async def create_order(self, order_event: OrderEvent) -> None:
        """Create a new order and record its initial state."""
        # 1. Rust Execution
        rust_side = RustSide.Buy if order_event.side == "BUY" else RustSide.Sell
        rust_type = (
            RustOrderType.Limit
            if order_event.order_type == "LIMIT"
            else RustOrderType.Stop
            if order_event.order_type == "STOP"
            else RustOrderType.Market
        )

        rust_order = RustOrder(
            order_event.order_id,
            order_event.symbol,
            rust_side,
            float(order_event.quantity),
            float(order_event.price) if order_event.price else 0.0,
            rust_type,
            order_event.timestamp,
        )
        self._rust_oms.create_order(rust_order)

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

        # 3. Persistence & Notifications
        await self._record_and_publish(
            "ORDER_CREATED",
            f"New order: {order_event.symbol}",
            {"order_id": order_event.order_id, "symbol": order_event.symbol},
            trace_id=getattr(order_event, "trace_id", None),
        )
        self._log.info(f"OMS | Order Created: {order_event.order_id} [{order_event.symbol}]")

    async def on_ack(self, order_id: str) -> None:
        """Handle exchange acknowledgement (ACK)."""
        rust_order = self._rust_oms.on_ack(order_id)
        await self._sync_order_state(rust_order)

    async def on_reject(self, order_id: str, reason: str) -> None:
        """Handle order rejection from exchange."""
        rust_order = self._rust_oms.on_reject(order_id)
        await self._sync_order_state(rust_order)
        await self._record_and_publish(
            "ORDER_REJECTED",
            reason,
            {"order_id": order_id},
            trace_id=None,  # We typically don't have trace_id on Reject if it comes from exchange later
        )
        self._log.error(f"OMS | Order Rejected: {order_id} - Reason: {reason}")

    async def cancel_order(self, order_id: str) -> None:
        """Handle order cancellation."""
        rust_order = self._rust_oms.on_cancel(order_id)
        await self._sync_order_state(rust_order)
        self._log.info(f"OMS | Order Cancelled: {order_id}")

    async def on_fill(self, fill_event: FillEvent) -> None:
        """Handle order fill and update positions via Rust core."""
        rust_order, rust_pos, rust_cash = self._rust_oms.on_fill(
            fill_event.order_id, float(fill_event.quantity), float(fill_event.price)
        )

        await self._sync_order_state(rust_order)

        py_pos = Position(
            symbol=rust_pos.symbol,
            quantity=Decimal(str(rust_pos.qty)),
            average_price=Decimal(str(rust_pos.avg_entry_price)),
            timestamp=datetime.utcnow(),
        )
        await self.state_store.set_position(py_pos)

        await self.state_store.set_portfolio_value(
            Decimal(str(rust_cash))
        )  # Should use equity() in real scenario

        await self._record_and_publish(
            "ORDER_FILLED",
            f"Fill: {fill_event.payload.symbol}",
            {
                "order_id": fill_event.order_id,
                "symbol": fill_event.payload.symbol,
                "quantity": str(fill_event.payload.quantity),
                "price": str(fill_event.payload.price),
                "side": fill_event.payload.side,
            },
            trace_id=getattr(fill_event, "trace_id", None),
        )
        self._log.info(f"OMS | Order Fill: {fill_event.order_id} | Qty: {fill_event.quantity}")

    async def _sync_order_state(self, rust_order: RustOrder) -> None:
        """Helper to sync Rust order state back to Python StateStore."""
        # Map Rust OrderStatus back to Python OrderState
        from qtrader.oms.order_fsm import get_state_from_status

        next_state = get_state_from_status(rust_order.status)
        await self.state_store.update_order(
            rust_order.id, lambda o: setattr(o, "status", next_state)
        )

    async def _record_and_publish(
        self, action: str, reason: str, metadata: dict[str, Any], trace_id: str | None = None
    ) -> None:
        """Unified logging and event bus publication."""
        from uuid import uuid4

        event = SystemEvent(
            source="UnifiedOMS",
            trace_id=trace_id or str(uuid4()),
            payload=SystemPayload(action=action, reason=reason, metadata=metadata),
        )
        await self.event_store.record_event(event)
        await self.event_bus.publish(event)
