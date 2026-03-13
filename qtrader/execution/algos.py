import asyncio

from qtrader.core.event import OrderEvent


class ExecutionAlgo:
    """Base class for execution algorithms."""
    def __init__(self, symbol: str, total_quantity: float) -> None:
        self.symbol = symbol
        self.total_quantity = total_quantity
        self.filled_quantity = 0.0

class TWAP(ExecutionAlgo):
    """Time-Weighted Average Price execution."""
    
    async def execute(self, duration_s: int, slices: int, bus: Any) -> None:
        slice_qty = self.total_quantity / slices
        interval = duration_s / slices
        
        for _ in range(slices):
            order = OrderEvent(
                symbol=self.symbol,
                order_type="MARKET",
                quantity=slice_qty,
                side="BUY" # Simplified
            )
            await bus.publish(order)
            self.filled_quantity += slice_qty
            await asyncio.sleep(interval)

class VWAP(ExecutionAlgo):
    """Volume-Weighted Average Price execution (simplified)."""
    
    async def execute(self, volume_profile: list[float], bus: Any) -> None:
        """Executes based on a provided volume profile."""
        for weight in volume_profile:
            slice_qty = self.total_quantity * weight
            order = OrderEvent(
                symbol=self.symbol,
                order_type="MARKET",
                quantity=slice_qty,
                side="BUY"
            )
            await bus.publish(order)
            self.filled_quantity += slice_qty
            # Wait for next bucket (simplified)
            await asyncio.sleep(60) 
