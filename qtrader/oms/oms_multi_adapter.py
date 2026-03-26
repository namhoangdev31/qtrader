"""OMS adapter for multi-exchange execution.

This adapter allows the orchestrator to use multiple exchanges via a smart router
while maintaining the existing OMSAdapter interface.
"""

import logging
from decimal import Decimal

from qtrader.core.types import AllocationWeights, OrderEvent, RiskMetrics
from qtrader.execution.execution_engine import ExchangeAdapter, ExecutionEngine
from qtrader.execution.multi_exchange_adapter import MultiExchangeAdapter
from qtrader.execution.smart_router import SmartOrderRouter

logger = logging.getLogger(__name__)


class MultiExchangeOMSAdapter:
    """
    OMS adapter that routes orders to the best exchange using a smart router.
    This adapter mimics the OMSAdapter interface by creating an OrderEvent
    from allocation weights and risk metrics, then submitting it via an
    internal ExecutionEngine that uses a MultiExchangeAdapter.
    """

    def __init__(
        self,
        exchange_adapters: dict[str, ExchangeAdapter],
        routing_mode: str = "smart",
        max_order_size: Decimal | None = None,
        split_size: Decimal | None = None,
        name: str = "MultiExchangeOMSAdapter",
    ):
        """
        Initialize multi-exchange OMS adapter.

        Args:
            exchange_adapters: Dictionary mapping exchange name to exchange adapter instance
            routing_mode: Routing strategy for the smart router ("best_price", "smart", "manual")
            max_order_size: Maximum order size for a single exchange (if set, orders will be split)
            split_size: Size of each split (if None, defaults to max_order_size)
            name: Name of this adapter
        """
        self.name = name
        self.logger = logger.getChild("MultiExchangeOMSAdapter")
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

        self.logger.info(
            f"MultiExchangeOMSAdapter initialized with {len(exchange_adapters)} exchanges"
        )

    async def start(self) -> None:
        """Start the internal execution engine."""
        if not self._engine_started:
            await self.execution_engine.start()
            self._engine_started = True
            self.logger.info("MultiExchangeOMSAdapter execution engine started")

    async def stop(self) -> None:
        """Stop the internal execution engine."""
        if self._engine_started:
            await self.execution_engine.stop()
            self._engine_started = False
            self.logger.info("MultiExchangeOMSAdapter execution engine stopped")

    async def create_order(
        self,
        allocation_weights: AllocationWeights,
        risk_metrics: RiskMetrics,
    ) -> OrderEvent:
        """
        Create an order based on allocation weights and risk metrics.
        This method conforms to the OMSAdapter interface.

        Args:
            allocation_weights: Portfolio allocation weights
            risk_metrics: Current risk metrics

        Returns:
            OrderEvent to be submitted to the OMS
        """
        # Delegate to a simple order creation logic (similar to the existing OMSAdapter)
        # We find the symbol with the highest weight and create a market order for it.
        # In a real implementation, this would be more sophisticated.

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
        # For now, assume long positions only (BUY)
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
                # Mark this as a multi-exchange order for submit_order to handle
                "_is_multi_exchange": True,
            }
        )

        self.logger.debug(
            f"Created order for {symbol}: weight={weight}, size={order_size}, side={side}"
        )
        return order_event

    async def submit_order(self, order_event: OrderEvent) -> None:
        """
        Submit an order to the exchange(s) via the internal execution engine.
        This method handles multi-exchange routing and order splitting.

        Args:
            order_event: OrderEvent to submit
        """
        # Check if this is a multi-exchange order (marked in create_order)
        if order_event.metadata.get("_is_multi_exchange", False):
            self.logger.info(
                f"Submitting multi-exchange order {order_event.order_id}"
            )
            # Start the execution engine if not already started
            if not self._engine_started:
                await self.start()
            # Submit the order via the execution engine
            # The execution engine will use the smart router to select the exchange
            # and handle retries, failover, etc.
            await self.execution_engine.execute_order(order_event)
        else:
            # For non-multi-exchange orders, we fall back to a single exchange.
            # We use the first exchange adapter as a default.
            # In a real system, we might want to allow configuration of the default exchange.
            if not self.exchange_adapters:
                self.logger.error("No exchange adapters available")
                return

            # Get the first exchange adapter
            exchange_adapter = list(self.exchange_adapters.values())[0]
            # We need to use an execution engine for this single exchange as well
            # to handle retries and failover consistently.
            # We can create a temporary execution engine or reuse the multi-exchange
            # adapter with only one exchange? But we don't want to start/stop the
            # multi-exchange engine for a single order.
            # For simplicity, we'll use the same execution engine (which uses the
            # multi-exchange adapter) even for single orders. The multi-exchange
            # adapter will still work with one exchange.
            if not self._engine_started:
                await self.start()
            await self.execution_engine.execute_order(order_event)

        # Note: The execution engine's execute_order method returns a tuple
        # (success, fill_event or None). We are not using the return value here
        # because the OMSAdapter interface's submit_order method is expected to
        # return None. In a real system, we might want to handle the result.
        # For now, we follow the interface and return nothing.
