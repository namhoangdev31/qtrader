"""OMS adapter for order creation and submission."""

import asyncio
from abc import ABC, abstractmethod
from decimal import Decimal

from qtrader.core.logger import logger
from qtrader.core.types import AllocationWeights, OrderEvent, RiskMetrics
from qtrader.execution.execution_engine import ExchangeAdapter, ExecutionEngine
from qtrader.execution.multi_exchange_adapter import MultiExchangeAdapter
from qtrader.execution.smart_router import SmartOrderRouter


class OMSAdapter(ABC):
    """Abstract base class for OMS adapters."""

    def __init__(self, name: str = "OMSAdapter"):
        self.name = name
        self.logger = logger

    @abstractmethod
    async def create_order(
        self, 
        allocation_weights: AllocationWeights, 
        risk_metrics: RiskMetrics
    ) -> OrderEvent:
        """Create an order based on allocation weights and risk metrics.
         
        Args:
            allocation_weights: Portfolio allocation weights
            risk_metrics: Current risk metrics
             
        Returns:
            OrderEvent to be submitted to the OMS
        """
        pass

    @abstractmethod
    async def cancel_all_orders(self):
        """Cancel all open orders.
        """
        pass


# Simple implementation that creates market orders based on allocation
class SimpleOMSAdapter(OMSAdapter):
    """Simple OMS adapter that creates market orders."""

    def __init__(self, name: str = "SimpleOMSAdapter"):
        super().__init__(name)

    async def create_order(
        self, 
        allocation_weights: AllocationWeights, 
        risk_metrics: RiskMetrics
    ) -> OrderEvent:
        """Create market orders based on allocation weights (simple implementation).
        
        Args:
            allocation_weights: Portfolio allocation weights
            risk_metrics: Current risk metrics
            
        Returns:
            OrderEvent to be submitted to the OMS
        """
        # In a real implementation, this would:
        # 1. Check risk limits
        # 2. Convert weights to target positions
        # 3. Calculate order sizes based on current positions
        # 4. Apply execution algorithms (TWAP, VWAP, etc.)
        # 5. Handle fractional shares, minimum order sizes, etc.
        
        # For now, we just create a simple market order for the first symbol
        # with weight > 0
        symbol = None
        weight = Decimal('0')
        
        for sym, w in allocation_weights.weights.items():
            if w > weight:
                symbol = sym
                weight = w
        
        if symbol is None or weight <= Decimal('0'):
            # No allocation to trade
            return OrderEvent(
                order_id="NO_TRADE",
                symbol="",
                timestamp=allocation_weights.timestamp,
                order_type="MARKET",
                side="BUY",  # Default, but quantity will be 0
                quantity=Decimal('0'),
                metadata={"reason": "no_allocation"}
            )
        
        # Simple order sizing: use weight as percentage of portfolio
        # In reality, this would be based on portfolio value and risk limits
        order_size = weight  # Simplified
        
        # Determine side based on signal (this would come from strategy in reality)
        # For now, assume long positions only
        side = "BUY"
        
        return OrderEvent(
            order_id=f"ORDER_{symbol}_{allocation_weights.timestamp.timestamp()}",
            symbol=symbol,
            timestamp=allocation_weights.timestamp,
            order_type="MARKET",
            side=side,
            quantity=order_size,
        metadata={
            "allocated_weight": float(weight),
            "risk_metrics": {
                "portfolio_var": float(risk_metrics.portfolio_var),
                "portfolio_volatility": float(risk_metrics.portfolio_volatility),
            }
        }
    )

    async def cancel_all_orders(self):
        """Cancel all open orders (simple implementation)."""
        self.logger.info("Cancelling all open orders (simple implementation)")
        # In a real implementation, we would call the OMS to cancel all orders
        # For now, we just log the action
        pass


class ExecutionOMSAdapter(OMSAdapter):
    """OMS adapter that uses ExecutionEngine with smart routing to submit orders."""

    def __init__(
        self,
        exchange_adapters: dict[str, ExchangeAdapter],
        routing_mode: str = "smart",
        max_order_size: Decimal | None = None,
        split_size: Decimal | None = None,
        name: str = "ExecutionOMSAdapter",
    ):
        """
        Initialize ExecutionOMSAdapter.

        Args:
            exchange_adapters: Dictionary mapping exchange name to exchange adapter instance
            routing_mode: Routing strategy ("best_price", "smart", "manual")
            max_order_size: Maximum order size for a single exchange (for splitting)
            split_size: Size of each split (if None, defaults to max_order_size)
            name: Name of this adapter
        """
        super().__init__(name)
        self.exchange_adapters = exchange_adapters
        self.routing_mode = routing_mode
        self.max_order_size = max_order_size
        self.split_size = split_size

        # Create the smart router
        self.router = SmartOrderRouter(
            exchanges=exchange_adapters,
            routing_mode=routing_mode,
            max_order_size=max_order_size,
            split_size=split_size,
        )

        # Create the multi-exchange adapter (which implements ExchangeAdapter)
        self.multi_exchange_adapter = MultiExchangeAdapter(
            exchanges=exchange_adapters,
            router=self.router,
            name="MultiExchangeAdapterInternal",
        )

        # Create the execution engine that uses the multi-exchange adapter
        self.execution_engine = ExecutionEngine(
            exchange_adapter=self.multi_exchange_adapter,
            logger=self.logger,
        )

        # Flag to track if the engine has been started
        self._engine_started = False
        self.logger.info(f"ExecutionOMSAdapter initialized with {len(exchange_adapters)} exchanges")

    async def start(self) -> None:
        """Start the internal execution engine."""
        if not self._engine_started:
            await self.execution_engine.start()
            self._engine_started = True
            self.logger.info("ExecutionOMSAdapter execution engine started")

    async def stop(self) -> None:
        """Stop the internal execution engine."""
        if self._engine_started:
            await self.execution_engine.stop()
            self._engine_started = False
            self.logger.info("ExecutionOMSAdapter execution engine stopped")

    async def create_order(
        self,
        allocation_weights: AllocationWeights,
        risk_metrics: RiskMetrics,
    ) -> OrderEvent:
        """
        Create and submit an order based on allocation weights and risk metrics.
        This method conforms to the OMSAdapter interface and actually submits the order.

        Args:
            allocation_weights: Portfolio allocation weights
            risk_metrics: Current risk metrics

        Returns:
            OrderEvent that was submitted
        """
        # Start the engine if not already started
        if not self._engine_started:
            await self.start()

        # Find the symbol with the highest weight
        symbol = None
        weight = Decimal('0')
        for sym, w in allocation_weights.weights.items():
            if w > weight:
                symbol = sym
                weight = w

        if symbol is None or weight <= Decimal('0'):
            # No allocation to trade
            return OrderEvent(
                order_id="NO_TRADE",
                symbol="",
                timestamp=allocation_weights.timestamp,
                order_type="MARKET",
                side="BUY",
                quantity=Decimal('0'),
                metadata={"reason": "no_allocation"}
            )

        # Simple order sizing: use weight as percentage of portfolio
        order_size = weight  # Simplified

        # Determine side based on signal (this would come from strategy in reality)
        # For now, assume long positions only
        side = "BUY"

        # Create the OrderEvent
        order_event = OrderEvent(
            order_id=f"ORDER_{symbol}_{allocation_weights.timestamp.timestamp()}",
            symbol=symbol,
            timestamp=allocation_weights.timestamp,
            order_type="MARKET",
            side=side,
            quantity=order_size,
            metadata={
                "allocated_weight": float(weight),
                "risk_metrics": {
                    "portfolio_var": float(risk_metrics.portfolio_var),
                    "portfolio_volatility": float(risk_metrics.portfolio_volatility),
                },
                "_submitted_via_execution": True,
            }
        )

        self.logger.debug(f"Created order for {symbol}: weight={weight}, size={order_size}, side={side}")

        # Submit the order via the execution engine (non-blocking)
        # We don't wait for the fill result, just fire and forget
        # In a real system, we might want to track fills via callbacks
        asyncio.create_task(self._submit_order(order_event))

        return order_event

    async def _submit_order(self, order_event: OrderEvent) -> None:
        """Submit order via execution engine and log result."""
        try:
            self.logger.info(f"Submitting order {order_event.order_id} via execution engine")
            success, result = await self.execution_engine.execute_order(order_event)
            if success:
                self.logger.info(f"Order {order_event.order_id} submitted successfully, result: {result}")
            else:
                self.logger.warning(f"Order {order_event.order_id} submission failed: {result}")
        except Exception as e:
            self.logger.error(f"Error submitting order {order_event.order_id}: {e}", exc_info=True)

    async def cancel_all_orders(self):
        """Cancel all open orders (delegated to execution engine)."""
        self.logger.info("Cancelling all open orders via ExecutionOMSAdapter")
        # In a real implementation, we would track pending orders and cancel them
        # For now, we just log the action
        pass