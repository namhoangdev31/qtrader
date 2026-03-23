"""Unit tests for multi-exchange execution system."""

import asyncio
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import pytest

from qtrader.core.types import OrderEvent, AllocationWeights, RiskMetrics, FillEvent
from qtrader.execution.execution_engine import (
    ExchangeAdapter,
    ExecutionEngine,
    SimulatedExchangeAdapter,
)
from qtrader.execution.smart_router import SmartOrderRouter
from qtrader.execution.multi_exchange_adapter import MultiExchangeAdapter
from qtrader.execution.oms_adapter import ExecutionOMSAdapter, OMSAdapter
from qtrader.execution.adapters.broker_bridge import BrokerAdapterBridge
from qtrader.execution.brokers.base import BrokerAdapter


class MockBrokerAdapter(BrokerAdapter):
    """Mock broker adapter for testing."""
    
    def __init__(self, name: str = "mock"):
        self.name = name
        self.orders = {}
        self.order_counter = 0
    
    async def submit_order(self, order: OrderEvent) -> str:
        self.order_counter += 1
        order_id = f"{self.name}_order_{self.order_counter}"
        self.orders[order_id] = order
        return order_id
    
    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            del self.orders[order_id]
            return True
        return False
    
    async def get_fills(self, order_id: str) -> list:
        return []
    
    async def get_balance(self) -> dict:
        return {"USD": 100000.0}


class TestSmartOrderRouter:
    """Test SmartOrderRouter."""
    
    @pytest.fixture
    def sample_adapters(self):
        """Create sample exchange adapters."""
        adapters = {
            "binance": SimulatedExchangeAdapter(name="binance"),
            "coinbase": SimulatedExchangeAdapter(name="coinbase"),
        }
        # Set different prices to test routing
        adapters["binance"].set_price("BTCUSDT", Decimal('50000'))
        adapters["coinbase"].set_price("BTCUSDT", Decimal('50100'))
        return adapters
    
    @pytest.fixture
    def router(self, sample_adapters):
        """Create SmartOrderRouter."""
        return SmartOrderRouter(
            exchanges=sample_adapters,
            routing_mode="smart",
            max_order_size=Decimal('10'),
            split_size=Decimal('5'),
        )
    
    def test_init(self, router):
        """Test router initialization."""
        assert router.routing_mode == "smart"
        assert len(router.exchanges) == 2
    
    @pytest.mark.asyncio
    async def test_route_single_order_best_price(self, sample_adapters):
        """Test routing single order with best price mode."""
        router = SmartOrderRouter(
            exchanges=sample_adapters,
            routing_mode="best_price",
        )
        
        order = OrderEvent(
            order_id="test1",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
        )
        
        market_data = {
            "binance": {"bids": [["49999", "1"]], "asks": [["50000", "1"]]},
            "coinbase": {"bids": [["50099", "1"]], "asks": [["50100", "1"]]},
        }
        
        routed = await router.route_order(order, market_data)
        assert len(routed) == 1
        # Should route to binance (lower ask for buy)
        assert routed[0].metadata["exchange"] == "binance"
    
    @pytest.mark.asyncio
    async def test_split_order(self, router):
        """Test order splitting."""
        order = OrderEvent(
            order_id="test_split",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('12'),  # > max_order_size (10)
        )
        
        market_data = {
            "binance": {"bids": [["49999", "1"]], "asks": [["50000", "10"]]},
            "coinbase": {"bids": [["50099", "1"]], "asks": [["50100", "10"]]},
        }
        
        routed = await router.route_order(order, market_data)
        # Should split into 3 slices of 5,5,2 (split_size=5)
        assert len(routed) == 3
        total_qty = sum(o.quantity for o in routed)
        assert total_qty == Decimal('12')


class TestMultiExchangeAdapter:
    """Test MultiExchangeAdapter."""
    
    @pytest.fixture
    def adapters(self):
        """Create test adapters."""
        adapters = {
            "binance": SimulatedExchangeAdapter(name="binance"),
            "coinbase": SimulatedExchangeAdapter(name="coinbase"),
        }
        # Set a price so market orders get filled
        adapters["binance"].set_price("BTCUSDT", Decimal('50000'))
        adapters["coinbase"].set_price("BTCUSDT", Decimal('50100'))
        return adapters
    
    @pytest.fixture
    def multi_adapter(self, adapters):
        """Create MultiExchangeAdapter."""
        router = SmartOrderRouter(exchanges=adapters, routing_mode="smart")
        return MultiExchangeAdapter(exchanges=adapters, router=router)
    
    @pytest.mark.asyncio
    async def test_send_order_success(self, multi_adapter):
        """Test successful order sending."""
        order = OrderEvent(
            order_id="multi1",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
        )
        
        success, result = await multi_adapter.send_order(order)
        assert success is True
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_send_order_with_fallback(self, multi_adapter):
        """Test fallback to second exchange."""
        # Make first adapter fail by mocking send_order
        failing_adapter = SimulatedExchangeAdapter(name="failing")
        async def failing_send(order):
            return False, "fail"
        failing_adapter.send_order = failing_send
        
        adapters = {
            "failing": failing_adapter,
            "working": SimulatedExchangeAdapter(name="working"),
        }
        # Set price for working adapter
        adapters["working"].set_price("BTCUSDT", Decimal('50000'))
        router = SmartOrderRouter(exchanges=adapters, routing_mode="smart")
        multi = MultiExchangeAdapter(exchanges=adapters, router=router)
        
        order = OrderEvent(
            order_id="fallback_test",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
        )
        
        success, result = await multi.send_order(order)
        # Should succeed via fallback (working adapter)
        assert success is True
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, multi_adapter):
        """Test order cancellation."""
        # First send an order
        order = OrderEvent(
            order_id="cancel_test",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="LIMIT",
            side="BUY",
            quantity=Decimal('1'),
            price=Decimal('50000'),  # limit price, not filled
        )
        success, order_id = await multi_adapter.send_order(order)
        assert success
        
        # Now cancel it
        success, error = await multi_adapter.cancel_order(order_id)
        assert success is True
        assert error is None


class TestExecutionOMSAdapter:
    """Test ExecutionOMSAdapter."""
    
    @pytest.fixture
    def adapters(self):
        """Create test adapters."""
        adapters = {
            "sim1": SimulatedExchangeAdapter(name="sim1"),
            "sim2": SimulatedExchangeAdapter(name="sim2"),
        }
        adapters["sim1"].set_price("AAPL", Decimal('150'))
        adapters["sim2"].set_price("AAPL", Decimal('151'))
        return adapters
    
    @pytest.fixture
    def oms_adapter(self, adapters):
        """Create ExecutionOMSAdapter."""
        return ExecutionOMSAdapter(
            exchange_adapters=adapters,
            routing_mode="smart",
            max_order_size=Decimal('100'),
            split_size=Decimal('50'),
        )
    
    @pytest.mark.asyncio
    async def test_create_order(self, oms_adapter):
        """Test order creation and submission."""
        allocation = AllocationWeights(
            timestamp=datetime.utcnow(),
            weights={"AAPL": Decimal('0.5')},
        )
        risk_metrics = RiskMetrics(
            timestamp=datetime.utcnow(),
            portfolio_var=Decimal('0.1'),
            portfolio_volatility=Decimal('0.2'),
            max_drawdown=Decimal('0.05'),
            leverage=Decimal('1.0'),
        )
        
        order = await oms_adapter.create_order(allocation, risk_metrics)
        assert order.symbol == "AAPL"
        assert order.quantity == Decimal('0.5')
        assert order.metadata["_submitted_via_execution"] is True
        
        # Give some time for async task to start
        await asyncio.sleep(0.1)
    
    @pytest.mark.asyncio
    async def test_create_order_no_allocation(self, oms_adapter):
        """Test order creation with no allocation."""
        allocation = AllocationWeights(
            timestamp=datetime.utcnow(),
            weights={},  # empty
        )
        risk_metrics = RiskMetrics(
            timestamp=datetime.utcnow(),
            portfolio_var=Decimal('0.1'),
            portfolio_volatility=Decimal('0.2'),
            max_drawdown=Decimal('0.05'),
            leverage=Decimal('1.0'),
        )
        
        order = await oms_adapter.create_order(allocation, risk_metrics)
        assert order.order_id == "NO_TRADE"
        assert order.quantity == Decimal('0')


class TestBrokerAdapterBridge:
    """Test BrokerAdapterBridge."""
    
    @pytest.fixture
    def mock_broker(self):
        """Create mock broker."""
        return MockBrokerAdapter(name="testbroker")
    
    @pytest.fixture
    def bridge(self, mock_broker):
        """Create bridge adapter."""
        return BrokerAdapterBridge(broker=mock_broker, name="TestBridge")
    
    @pytest.mark.asyncio
    async def test_send_order(self, bridge):
        """Test order sending via bridge."""
        order = OrderEvent(
            order_id="bridge1",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
        )
        
        success, result = await bridge.send_order(order)
        assert success is True
        assert result == "testbroker_order_1"
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, bridge):
        """Test order cancellation via bridge."""
        # First send an order
        order = OrderEvent(
            order_id="bridge_cancel",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
        )
        success, order_id = await bridge.send_order(order)
        assert success
        
        # Cancel it
        success, error = await bridge.cancel_order(order_id)
        assert success is True
        assert error is None


class TestExecutionEngineIntegration:
    """Test ExecutionEngine with multi-exchange setup."""
    
    @pytest.mark.asyncio
    async def test_execution_with_multi_adapter(self):
        """Test ExecutionEngine with SimulatedExchangeAdapter (single)."""
        adapter = SimulatedExchangeAdapter(name="sim")
        adapter.set_price("BTCUSDT", Decimal('50000'))
        
        engine = ExecutionEngine(exchange_adapter=adapter)
        
        order = OrderEvent(
            order_id="engine_test",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
            price=Decimal('50000'),  # optional, but helps
        )
        
        success, result = await engine.execute_order(order)
        assert success is True
        assert isinstance(result, FillEvent)  # result should be a FillEvent
    
    @pytest.mark.asyncio
    async def test_execution_retry_logic(self):
        """Test retry logic in ExecutionEngine."""
        # Create a failing adapter that fails first attempt then succeeds with fill
        class FailingSimulatedAdapter(SimulatedExchangeAdapter):
            def __init__(self):
                super().__init__(name="failing_sim")
                self.attempt_count = 0
                self.set_price("BTCUSDT", Decimal('50000'))
            
            async def send_order(self, order):
                self.attempt_count += 1
                if self.attempt_count < 2:
                    return False, "temporary failure"
                # On second attempt, call super to generate fill event
                return await super().send_order(order)
        
        adapter = FailingSimulatedAdapter()
        engine = ExecutionEngine(
            exchange_adapter=adapter,
            max_retry_attempts=1,  # total attempts = 2 (0,1)
            retry_delay_base=0.01,
        )
        
        order = OrderEvent(
            order_id="retry_test",
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('1'),
        )
        
        success, result = await engine.execute_order(order)
        assert success is True
        assert adapter.attempt_count == 2


class TestConfiguration:
    """Test configuration loading."""
    
    def test_load_yaml_config(self, tmp_path):
        """Test loading YAML configuration."""
        from qtrader.execution.config import ExecutionConfig
        
        config_content = """
exchanges:
  binance:
    enabled: true
    adapter_type: "binance"
    api_key: "test_key"
    api_secret: "test_secret"
    testnet: true

routing:
  mode: "smart"
  max_order_size: 10000.0
  split_size: 5000.0
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(config_content)
        
        config = ExecutionConfig.from_yaml(str(config_file))
        assert config.is_exchange_enabled("binance")
        assert config.get_routing_mode() == "smart"
        assert config.get_max_order_size() == Decimal('10000')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])