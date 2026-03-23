import pytest
from unittest.mock import MagicMock
from qtrader.execution.smart_router import SmartRouter
from qtrader.core.types import Order, Side

def test_smart_router_initialization():
    router = SmartRouter(exchanges=["binance", "coinbase"])
    assert "binance" in router.exchanges
    assert "coinbase" in router.exchanges

def test_smart_router_route_order():
    router = SmartRouter(exchanges=["binance"])
    mock_exchange = MagicMock()
    mock_exchange.get_best_bid.return_value = 100.0
    router.add_exchange_client("binance", mock_exchange)
    
    order = Order(symbol="BTC", side=Side.Sell, quantity=1.0, price=0.0) # Market order
    routed_exchange = router.route(order)
    
    assert routed_exchange == "binance"
    mock_exchange.get_best_bid.assert_called_once()
