import asyncio
import logging
import uuid
from typing import Dict, List

from qtrader.core.event import EventType, FillEvent, MarketDataEvent, OrderEvent
from qtrader.output.execution.brokers.base import BrokerAdapter

_LOG = logging.getLogger("qtrader.broker.simulator")

class SimulatorBrokerAdapter(BrokerAdapter):
    """
    High-fidelity local paper trading simulator.
    
    Acts as a bridge between the EventBus and the OMS, fulfilling orders
    locally based on live market data events without hitting real exchange APIs.
    """

    def __init__(
        self,
        starting_balances: Dict[str, float] | None = None,
        latency_ms: float = 50.0,
        commission_bps: float = 5.0,
    ) -> None:
        self._balances = starting_balances or {"USD": 100_000.0}
        self._latency = latency_ms / 1000.0
        self._commission_rate = commission_bps / 10000.0
        
        self._orders: Dict[str, OrderEvent] = {}
        self._fills: Dict[str, List[FillEvent]] = {}
        self._quotes: Dict[str, Dict[str, float]] = {}  # symbol -> {"bid": .., "ask": ..}
        self._positions: Dict[str, float] = {}

    def update_quote(self, symbol: str, bid: float, ask: float) -> None:
        """Update the internal book for price-accurate fills."""
        self._quotes[symbol] = {"bid": bid, "ask": ask}

    async def submit_order(self, order: OrderEvent) -> str:
        """Process order locally: simulates network latency and local matching."""
        broker_oid = str(uuid.uuid4())
        self._orders[broker_oid] = order
        
        # Simulate network latency
        await asyncio.sleep(self._latency)
        
        # Immediate fill for market orders if price is available
        if order.order_type.upper() == "MARKET":
            fill = self._generate_fill(broker_oid, order)
            if fill:
                self._record_fill(broker_oid, fill)
        
        return broker_oid

    async def cancel_order(self, order_id: str) -> bool:
        """Simulate order cancellation."""
        await asyncio.sleep(self._latency)
        if order_id in self._orders:
            self._orders.pop(order_id)
            return True
        return False

    async def get_fills(self, order_id: str) -> List[FillEvent]:
        """Return cached simulated fills."""
        return self._fills.get(order_id, [])

    async def get_balance(self) -> dict:
        """Return simulated account balance."""
        return self._balances

    def _generate_fill(self, broker_oid: str, order: OrderEvent) -> FillEvent | None:
        """Simulates a fill based on the current best bid/ask."""
        quote = self._quotes.get(order.symbol)
        if not quote:
            # Fallback to order price if no quote, otherwise can't fill
            price = order.price or 0.0
            if price <= 0: return None
        else:
            # Fill at ask if buying, bid if selling (slippage included in the spread)
            price = quote["ask"] if order.side.upper() == "BUY" else quote["bid"]
        
        commission = price * order.quantity * self._commission_rate
        
        return FillEvent(
            type=EventType.FILL,
            symbol=order.symbol,
            quantity=order.quantity,
            price=price,
            commission=commission,
            side=order.side,
            order_id=order.order_id or broker_oid,
            fill_id=str(uuid.uuid4())
        )

    def _record_fill(self, broker_oid: str, fill: FillEvent) -> None:
        """Update internal simulated state (balance/positions)."""
        self._fills.setdefault(broker_oid, []).append(fill)
        
        # Net balance impacts
        side_mult = 1.0 if fill.side.upper() == "BUY" else -1.0
        cost = fill.quantity * fill.price + fill.commission
        
        # Crude balance logic for paper trading
        self._balances["USD"] = self._balances.get("USD", 0.0) - (side_mult * cost)
        self._positions[fill.symbol] = self._positions.get(fill.symbol, 0.0) + (side_mult * fill.quantity)
        
        _LOG.info("Simulated FILL: %s %s @ %s", fill.side, fill.quantity, fill.price)
