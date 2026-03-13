import uuid

from qtrader.core.bus import EventBus
from qtrader.core.event import FillEvent, MarketDataEvent, OrderEvent


class SimulatedBroker:
    """Simulates exchange execution for backtesting."""

    def __init__(self, bus: EventBus, commission_rate: float = 0.0001) -> None:
        self.bus = bus
        self.commission_rate = commission_rate
        self.latest_prices: dict[str, float] = {}
        self.active_orders: dict[str, OrderEvent] = {}

    async def on_market_data(self, event: MarketDataEvent) -> None:
        """Update internal price state for fills."""
        price = event.data.get("close")
        if price:
            self.latest_prices[event.symbol] = price
            await self._process_active_orders(event.symbol, price)

    async def on_order(self, event: OrderEvent) -> None:
        """Receive order and attempt to fill it."""
        # In a simple backtest, we fill immediately at last known price or next market bar
        price = self.latest_prices.get(event.symbol)
        if price:
            await self._execute_fill(event, price)
        else:
            # Store order until we get a price
            order_id = event.order_id or str(uuid.uuid4())
            self.active_orders[order_id] = event

    async def _process_active_orders(self, symbol: str, price: float) -> None:
        to_fill = []
        for oid, order in self.active_orders.items():
            if order.symbol == symbol:
                to_fill.append(oid)
        
        for oid in to_fill:
            order = self.active_orders.pop(oid)
            await self._execute_fill(order, price)

    async def _execute_fill(self, order: OrderEvent, price: float) -> None:
        commission = price * order.quantity * self.commission_rate
        fill = FillEvent(
            symbol=order.symbol,
            quantity=order.quantity,
            price=price,
            commission=commission,
            side=order.side,
            order_id=order.order_id or "unknown",
            fill_id=str(uuid.uuid4())
        )
        await self.bus.publish(fill)
