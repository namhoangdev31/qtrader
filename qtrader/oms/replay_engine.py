from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional

from qtrader.core.events import (
    BaseEvent, MarketEvent, OrderEvent, FillEvent, RiskEvent, EventType
)
from qtrader.core.event_store import BaseEventStore
from qtrader.core.state_store import SystemState, Position, Order, RiskState

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
        # This uses the partitioned retrieval logic
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
        mid_price = Decimal(str((event.bid + event.ask) / 2))
        
        # Re-calculate unrealized PnL based on replayed market ticks
        pos.market_value = pos.quantity * mid_price
        if pos.quantity != 0:
            pos.unrealized_pnl = pos.market_value - (pos.quantity * pos.average_price)
        else:
            pos.unrealized_pnl = Decimal('0')

    def _handle_order(self, state: SystemState, event: OrderEvent) -> None:
        """Track active orders in the state."""
        payload = event.payload
        state.active_orders[payload.order_id] = Order(
            order_id=payload.order_id,
            symbol=payload.symbol,
            side=payload.action,
            order_type=payload.order_type,
            quantity=Decimal(str(payload.quantity)),
            price=Decimal(str(payload.price)) if payload.price else None,
            status="ACK"
        )

    def _handle_fill(self, state: SystemState, event: FillEvent) -> None:
        """Update positions and close orders upon fill."""
        payload = event.payload
        symbol = payload.symbol
        
        if symbol not in state.positions:
            state.positions[symbol] = Position(symbol=symbol)
            
        pos = state.positions[symbol]
        qty_filled = Decimal(str(payload.quantity))
        qty_delta = qty_filled if payload.side == "BUY" else -qty_filled
        fill_price = Decimal(str(payload.price))
        
        # Calculate new average cost
        new_qty = pos.quantity + qty_delta
        if new_qty != 0:
            if (qty_delta * pos.quantity) >= 0:
                # Adding to or starting position
                total_cost = (pos.quantity * pos.average_price) + (qty_filled * fill_price)
                pos.average_price = total_cost / abs(new_qty)
            else:
                # Reducing position - Average price doesn't change in simple accounting 
                # unless we cross zero (flip)
                if (pos.quantity * new_qty) < 0:
                    pos.average_price = fill_price
        else:
            pos.average_price = Decimal('0')
            
        pos.quantity = new_qty
        
        # Remove from active orders if fully filled
        if payload.order_id in state.active_orders:
            # Note: In a real system we'd check partial fills, but here we assume full fill for simplicity
            del state.active_orders[payload.order_id]

    def _handle_risk(self, state: SystemState, event: RiskEvent) -> None:
        """Update risk multipliers and state limits."""
        payload = event.payload
        state.current_risk_multiplier = Decimal(str(payload.value))
        state.risk_state.max_drawdown = Decimal(str(payload.metrics.get("max_drawdown", 0)))

    @staticmethod
    def calculate_state_hash(state: SystemState) -> str:
        """
        Generate a verifiable SHA-256 fingerprint of the system state.
        Used to ensure deterministic reproducibility.
        """
        import hashlib
        
        # Sort keys to ensure stable string representation
        pos_parts = []
        for sym, pos in sorted(state.positions.items()):
            pos_parts.append(f"{sym}:{pos.quantity}:{pos.average_price:.4f}")
            
        ord_parts = sorted(state.active_orders.keys())
        
        fingerprint = f"POS:{'|'.join(pos_parts)};ORD:{'|'.join(ord_parts)};RISK:{state.current_risk_multiplier}"
        return hashlib.sha256(fingerprint.encode()).hexdigest()


class ReplayError(Exception):
    """Raised when the replay engine encounters a sequence violation or corrupted data."""
    pass
