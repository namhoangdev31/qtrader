import pytest
from unittest.mock import MagicMock
from qtrader.oms.interface import OrderManagementSystem
from qtrader.core.types import Order, Side

class MockOMS(OrderManagementSystem):
    def __init__(self):
        self.orders = {}
        
    def submit_order(self, order: Order) -> str:
        if order.quantity <= 0:
            raise ValueError("Quantity must be positive")
        order_id = f"ord_{len(self.orders) + 1}"
        self.orders[order_id] = order
        return order_id
        
    def cancel_order(self, order_id: str) -> bool:
        if order_id not in self.orders:
            return False
        # Simulating a race condition where order is already filled
        if self.orders[order_id].quantity == -1.0:
            return False 
        del self.orders[order_id]
        return True
        
    def get_position(self, symbol: str) -> float:
        return 10.0

def test_oms_interface_impl_happy_path():
    oms = MockOMS()
    order = Order(symbol="BTC", side=Side.Buy, quantity=1.0, price=100.0)
    
    order_id = oms.submit_order(order)
    assert order_id == "ord_1"
    assert oms.cancel_order(order_id) is True
    assert oms.get_position("BTC") == 10.0

def test_oms_interface_invalid_order_size():
    oms = MockOMS()
    order = Order(symbol="BTC", side=Side.Sell, quantity=-10.0, price=50000.0)
    # A robust OMS should outright reject negative or zero size orders before sending to network
    with pytest.raises(ValueError):
        oms.submit_order(order)
        
def test_oms_interface_cancel_nonexistent_order():
    oms = MockOMS()
    assert oms.cancel_order("phantom_123") is False

def test_oms_interface_cancel_race_condition():
    oms = MockOMS()
    order = Order(symbol="BTC", side=Side.Buy, quantity=1.0, price=100.0)
    order_id = oms.submit_order(order)
    
    # Simulate order being filled completely right before cancel
    oms.orders[order_id].quantity = -1.0 
    
    assert oms.cancel_order(order_id) is False
