from qtrader.core.event import OrderEvent, RiskEvent
from qtrader.risk.base import RiskManager


class SimpleRiskManager(RiskManager):
    """Basic risk manager with volume and concentration limits."""

    def __init__(
        self, 
        max_order_value: float = 100000.0, 
        max_position_value: float = 500000.0
    ) -> None:
        self.max_order_value = max_order_value
        self.max_position_value = max_position_value
        # In a real system, we'd track current positions here or via a PositionManager
        self.current_positions: dict[str, float] = {} 

    def check_order(self, order: OrderEvent) -> RiskEvent | None:
        order_value = (order.price or 0.0) * order.quantity
        
        # Check order size
        if order_value > self.max_order_value:
            return RiskEvent(
                reason=f"Order value {order_value} exceeds max {self.max_order_value}",
                action="BLOCK"
            )
            
        return None
