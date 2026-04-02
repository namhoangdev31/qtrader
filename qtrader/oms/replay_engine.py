from __future__ import annotations

import hashlib
import logging
import time

from qtrader.core.decimal_adapter import d, math_authority
from qtrader.core.event_store import BaseEventStore
from qtrader.core.events import BaseEvent, FillEvent, MarketEvent, OrderEvent, RiskEvent
from qtrader.core.state_store import Order, Position, SystemState

logger = logging.getLogger(__name__)


class ReplayEngine:
    """
    Deterministic system state reconstruction engine.
    Uses an Event-Sourcing approach to rebuild the authoritative system state 
    from persistent event logs.
    
    Mathematical Model: State(t) = fold(events[0...t])
    """

    def __init__(self, event_store: BaseEventStore) -> None:
        """
        Initialize the ReplayEngine.
        
        Args:
            event_store: The persistent source of truth for events.
        """
        self._event_store = event_store

    async def replay(
        self, 
        partition: str | None = None, 
        start_offset: int | None = None, 
        end_offset: int | None = None
    ) -> SystemState:
        """
        Reconstruct the system state by replaying events in strict deterministic order.
        
        Returns:
            SystemState: The final reconstructed state.
        """
        start_perf = time.perf_counter()
        
        # 1. Fetch events from the store
        events = await self._event_store.get_events(
            partition=partition, 
            start_offset=start_offset, 
            end_offset=end_offset
        )
        
        # 2. Strict Deterministic Sorting
        # Events MUST be sorted by:
        # 1. Timestamp (Global sequence)
        # 2. Partition Key (Deterministic tie-breaking)
        # 3. Offset (Local per-partition sequence)
        events.sort(key=lambda x: (x.timestamp, x.partition_key or "", x.offset or 0))
        
        # 3. State Folding
        state = SystemState()
        for event in events:
            try:
                self._apply_event(state, event)
            except Exception as e:
                logger.error(f"Replay failed at event {event.event_id} (offset {event.offset}): {e}")
                raise ReplayError(f"Replay stalled: {e}") from e
                
        duration_ms = (time.perf_counter() - start_perf) * 1000
        logger.info(f"Replay complete: {len(events)} events processed in {duration_ms:.2f}ms")
        
        return state

    def _apply_event(self, state: SystemState, event: BaseEvent) -> None:
        """
        Dispatching logic to handle state transitions per event type.
        """
        if isinstance(event, MarketEvent):
            self._handle_market(state, event)
        elif isinstance(event, OrderEvent):
            self._handle_order(state, event)
        elif isinstance(event, FillEvent):
            self._handle_fill(state, event)
        elif isinstance(event, RiskEvent):
            self._handle_risk(state, event)

    def _handle_market(self, state: SystemState, event: MarketEvent) -> None:
        """Update mark-to-market prices and PnL."""
        symbol = event.symbol
        if symbol not in state.positions:
            state.positions[symbol] = Position(symbol=symbol)
            
        pos = state.positions[symbol]
        # Mid price calculation using math_authority
        mid_price = (event.bid + event.ask) / d(2)
        
        # Re-calculate unrealized PnL based on replayed market ticks
        pos.market_value = pos.quantity * mid_price
        if pos.quantity != 0:
            pos.unrealized_pnl = pos.market_value - (pos.quantity * pos.average_price)
        else:
            pos.unrealized_pnl = d(0)

    def _handle_order(self, state: SystemState, event: OrderEvent) -> None:
        """Track active orders in the state."""
        state.active_orders[event.order_id] = Order(
            order_id=event.order_id,
            symbol=event.symbol,
            side=event.action,
            order_type=event.payload.order_type,
            quantity=event.quantity,
            price=event.payload.price,
            status="ACK"
        )

    def _handle_fill(self, state: SystemState, event: FillEvent) -> None:
        """Update positions and close orders upon fill."""
        symbol = event.payload.symbol
        
        if symbol not in state.positions:
            state.positions[symbol] = Position(symbol=symbol)
            
        pos = state.positions[symbol]
        qty_filled = event.payload.quantity
        qty_delta = qty_filled if event.payload.side == "BUY" else -qty_filled
        fill_price = event.payload.price
        
        # Calculate new average cost
        new_qty = pos.quantity + qty_delta
        if new_qty != 0:
            if (qty_delta * pos.quantity) >= 0:
                # Adding to or starting position
                total_cost = (pos.quantity * pos.average_price) + (qty_filled * fill_price)
                new_avg = total_cost / abs(new_qty)
                pos.average_price = math_authority.to_price(new_avg)
            else:
                # Reducing position - Average price remains same, realized P&L updated
                # Note: This is an event-sourced simplification. Full FIFO logic in OMS.
                if (pos.quantity * new_qty) < 0:
                    pos.average_price = fill_price
                
                realized = (fill_price - pos.average_price) * abs(qty_delta) * (d(1) if pos.quantity > 0 else d(-1))
                pos.realized_pnl += realized
        else:
            realized = (fill_price - pos.average_price) * abs(qty_delta) * (d(1) if pos.quantity > 0 else d(-1))
            pos.realized_pnl += realized
            pos.average_price = d(0)
            
        pos.quantity = new_qty
        
        # Remove from active orders if fully filled
        if event.order_id in state.active_orders:
            del state.active_orders[event.order_id]

    def _handle_risk(self, state: SystemState, event: RiskEvent) -> None:
        """Update risk multipliers and state limits."""
        state.current_risk_multiplier = event.payload.value
        state.risk_state.max_drawdown = event.payload.metrics.get("max_drawdown", d(0))

    @staticmethod
    def calculate_state_hash(state: SystemState) -> str:
        """
        Generate a verifiable SHA-256 fingerprint of the system state.
        Used to ensure deterministic reproducibility (ε=0).
        """
        # Sort keys to ensure stable string representation
        pos_parts = []
        for sym, pos in sorted(state.positions.items()):
            # Use raw string representation of Decimal for exact match
            pos_parts.append(f"{sym}:{pos.quantity}:{pos.average_price}")
            
        ord_parts = sorted(state.active_orders.keys())
        
        fingerprint = f"POS:{'|'.join(pos_parts)};ORD:{'|'.join(ord_parts)};RISK:{state.current_risk_multiplier}"
        return hashlib.sha256(fingerprint.encode()).hexdigest()


class ReplayError(Exception):
    """Raised when the replay engine encounters a sequence violation or corrupted data."""
    pass


class ReplayError(Exception):
    """Raised when the replay engine encounters a sequence violation or corrupted data."""
    pass
