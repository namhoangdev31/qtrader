from typing import Dict, List, Any
from qtrader.execution.brokers.base import BrokerAdapter
from qtrader.core.event import OrderEvent, FillEvent

class UnifiedOMS:
    """
    Centralized Order Management System for Multi-Venue trading.
    Aggregates state from multiple brokers and provides a unified risk/pnl view.
    """
    
    def __init__(self) -> None:
        self.adapters: Dict[str, BrokerAdapter] = {}
        self.live_orders: Dict[str, OrderEvent] = {} # broker_oid -> Order
        self.positions: Dict[str, Dict[str, float]] = {} # venue -> asset -> qty

    def add_venue(self, name: str, adapter: BrokerAdapter) -> None:
        self.adapters[name] = adapter
        self.positions[name] = {}

    async def sync_all_balances(self) -> None:
        """Polls all venues for current balances/positions."""
        for name, adapter in self.adapters.items():
            try:
                self.positions[name] = await adapter.get_balance()
            except Exception as e:
                print(f"OMS | Failed to sync {name}: {e}")

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
