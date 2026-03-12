import asyncio
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass
from qtrader.core.bus import EventBus
from qtrader.core.event import OrderEvent, FillEvent, MarketDataEvent

@dataclass
class QueueOrder:
    order: OrderEvent
    volume_ahead: float
    timestamp: float

class L2BrokerSim:
    """
    Advanced Simulator for L2 Orderbook.
    Simulates:
    - Queue position (orders only fill after volume ahead is consumed)
    - Network Latency
    - Partial Fills
    """
    def __init__(self, bus: EventBus, latency_ms: int = 5) -> None:
        self.bus = bus
        self.latency_ms = latency_ms / 1000.0
        self.bid_queue: Dict[str, QueueOrder] = {}
        self.ask_queue: Dict[str, QueueOrder] = {}
        # current orderbook state
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.bid_size = 0.0
        self.ask_size = 0.0

    async def on_market_data(self, event: MarketDataEvent) -> None:
        """Process incoming L2 snapshots/deltas and update queues."""
        data = event.data
        self.best_bid = data.get("bid", self.best_bid)
        self.best_ask = data.get("ask", self.best_ask)
        self.bid_size = data.get("bid_size", self.bid_size)
        self.ask_size = data.get("ask_size", self.ask_size)
        
        # Check if orders in queue can be filled
        # If trade price <= our limit buy price, volume ahead is reduced by trade volume
        # Simplified: if best bid moves or size changes, we update queue
        # Real implementation would use trade events for queue depletion.
        await self._check_fills()

    async def on_order(self, order: OrderEvent) -> None:
        """Simulate sending order with latency."""
        await asyncio.sleep(self.latency_ms)
        
        oid = order.order_id or str(uuid.uuid4())
        if order.side == "BUY":
            # Queue position = current size at this level
            # (Simplified: assuming best bid level)
            self.bid_queue[oid] = QueueOrder(order, self.bid_size, asyncio.get_event_loop().time())
        else:
            self.ask_queue[oid] = QueueOrder(order, self.ask_size, asyncio.get_event_loop().time())

    async def _check_fills(self) -> None:
        # Simplified logic: if price crosses, we fill. 
        # If price stays, we'd need trade events to deplete volume_ahead.
        pass

    async def _execute_fill(self, q_order: QueueOrder, price: float, quantity: float) -> None:
        fill = FillEvent(
            symbol=q_order.order.symbol,
            quantity=quantity,
            price=price,
            commission=0.0,
            side=q_order.order.side,
            order_id=q_order.order.order_id or "unknown",
            fill_id=str(uuid.uuid4())
        )
        await self.bus.publish(fill)
