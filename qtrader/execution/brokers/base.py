from typing import Protocol, runtime_checkable, List
from qtrader.core.event import OrderEvent, FillEvent

@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol for connecting to live brokers/exchanges."""
    
    async def submit_order(self, order: OrderEvent) -> str:
        """Submit order and return broker order ID."""
        ...

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        ...

    async def get_fills(self, order_id: str) -> List[FillEvent]:
        """Fetch fills for a specific order."""
        ...

    async def get_balance(self) -> dict:
        """Fetch account balances."""
        ...
