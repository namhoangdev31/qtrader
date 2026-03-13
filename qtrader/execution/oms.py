import logging
from typing import Any

from qtrader.core.event import OrderEvent
from qtrader.execution.brokers.base import BrokerAdapter


class UnifiedOMS:
    """
    Centralized Order Management System for Multi-Venue trading.
    Aggregates state from multiple brokers and provides a unified risk/pnl view.
    """
    
    def __init__(self) -> None:
        self.adapters: dict[str, BrokerAdapter] = {}
        self.live_orders: dict[str, OrderEvent] = {} # broker_oid -> Order
        self.positions: dict[str, dict[str, float]] = {} # venue -> asset -> qty
        self.market_state: dict[tuple[str, str], dict[str, Any]] = {}  # (venue, symbol) -> L1/L2 snapshot
        self.pending_order_context: dict[str, dict[str, Any]] = {}  # symbol -> context (order_size, daily_volume, sigma)
        self._log = logging.getLogger("qtrader.oms")

    def add_venue(self, name: str, adapter: BrokerAdapter) -> None:
        self.adapters[name] = adapter
        self.positions[name] = {}

    async def sync_all_balances(self) -> None:
        """Polls all venues for current balances/positions."""
        for name, adapter in self.adapters.items():
            try:
                self.positions[name] = await adapter.get_balance()
            except Exception as e:
                self._log.exception("Failed to sync balances for %s", name, exc_info=e)

    def update_market_state(self, venue: str, symbol: str, state: dict[str, Any]) -> None:
        """Stores the latest market snapshot for routing decisions (SOR)."""
        key = (venue, symbol)
        existing = self.market_state.get(key, {})
        merged = {**existing, **state}
        self.market_state[key] = merged

    def get_market_state(self, venue: str, symbol: str) -> dict[str, Any]:
        return self.market_state.get((venue, symbol), {})

    def set_pending_order_context(self, symbol: str, context: dict[str, Any]) -> None:
        """Stores per-symbol order context for SOR/impact calculations."""
        self.pending_order_context[symbol] = context

    def get_pending_order_context(self, symbol: str) -> dict[str, Any]:
        return self.pending_order_context.get(symbol, {})

    async def route_order(self, venue: str, order: OrderEvent) -> str:
        """Routes an order to a specific venue and tracks it."""
        if venue not in self.adapters:
            raise ValueError(f"Venue {venue} not found")
            
        adapter = self.adapters[venue]
        broker_oid = await adapter.submit_order(order)
        self.live_orders[broker_oid] = order
        return broker_oid

    def get_total_exposure(self, asset: str) -> float:
        """Calculates total exposure of an asset across all venues."""
        total = 0.0
        for venue_pos in self.positions.values():
            total += venue_pos.get(asset, 0.0)
        return total
