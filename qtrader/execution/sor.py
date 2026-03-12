from typing import List, Dict, Tuple
from qtrader.execution.oms import UnifiedOMS
from qtrader.core.event import OrderEvent

class SmartOrderRouter:
    """
    Finds the best venue(s) for a given order based on liquidity and price.
    """
    
    def __init__(self, oms: UnifiedOMS) -> None:
        self.oms = oms

    async def get_best_venue(self, symbol: str, side: str) -> str:
        """
        Logic to poll orderbooks from multiple venues and pick the best one.
        (Simplified version: returns venue with highest balance/liquidity)
        """
        best_venue = None
        max_liquidity = -1.0
        
        for name, adapter in self.oms.adapters.items():
            # In real SOR, we would fetch snapshot L1/L2 here
            # For now, we use cached balance as a proxy for 'capability'
            balance = self.oms.positions.get(name, {}).get("USDT", 0.0)
            if balance > max_liquidity:
                max_liquidity = balance
                best_venue = name
                
        return best_venue or list(self.oms.adapters.keys())[0]

    async def split_order(self, order: OrderEvent, venues: List[str]) -> List[Tuple[str, OrderEvent]]:
        """Splits a large order into multiple venues (Arbitrage/Liquidity capture)."""
        # Logic for proportioning order size based on book depth
        portions = []
        qty_per_venue = order.quantity / len(venues)
        for v in venues:
            new_order = OrderEvent(
                symbol=order.symbol,
                side=order.side,
                quantity=qty_per_venue,
                order_type=order.order_type,
                price=order.price
            )
            portions.append((v, new_order))
        return portions
