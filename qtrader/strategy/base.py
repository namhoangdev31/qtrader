from typing import Protocol, runtime_checkable, List
from qtrader.core.event import SignalEvent, OrderEvent


@runtime_checkable
class Strategy(Protocol):
    """Protocol for converting signals into orders."""

    def on_signal(self, event: SignalEvent) -> List[OrderEvent]:
        ...


class BaseStrategy:
    """Base class for strategies with common logic."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def create_order(
        self, 
        quantity: float, 
        side: str, 
        order_type: str = "MARKET", 
        price: float | None = None
    ) -> OrderEvent:
        return OrderEvent(
            symbol=self.symbol,
            order_type=order_type,
            quantity=quantity,
            price=price,
            side=side
        )
