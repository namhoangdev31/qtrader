"""OMS adapter for order creation and submission."""

import asyncio
import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from qtrader.core.execution_guard import require_initialized
from qtrader.core.logger import logger
from qtrader.core.types import AllocationWeights, OrderEvent, RiskMetrics
from qtrader.execution.execution_engine import ExchangeAdapter, ExecutionEngine
from qtrader.oms.order_management_system import UnifiedOMS



class OMSAdapter(ABC):
    """Abstract base class for OMS adapters."""

    def __init__(self, name: str = "OMSAdapter") -> None:
        self.name = name
        self.logger = logger

    @require_initialized
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

    @require_initialized
    @abstractmethod
    async def cancel_all_orders(self):
        """Cancel all open orders.
        """
        pass

    def _get_highest_weight(self, allocation_weights: AllocationWeights) -> tuple[str | None, Decimal]:
        """Helper to find the symbol with the highest allocation weight."""
        symbol = None
        max_weight = Decimal('0')
        for sym, w in allocation_weights.weights.items():
            if w > max_weight:
                symbol = sym
                max_weight = w
        return symbol, max_weight

    def _create_empty_order(self, timestamp: Any) -> OrderEvent:
        """Helper to create a zero-quantity order event."""
        ts_val = int(timestamp.timestamp() * 1_000_000) if hasattr(timestamp, "timestamp") else int(time.time() * 1_000_000)
        
        from qtrader.core.events import OrderPayload
        return OrderEvent(
            source="OMSAdapter",
            timestamp=ts_val,
            payload=OrderPayload(
                order_id="NO_TRADE",
                symbol="",
                action="BUY", # Placeholder for empty
                quantity=Decimal('0'),
                order_type="MARKET",
                metadata={"reason": "no_allocation"}
            )
        )


# Simple implementation that creates market orders based on allocation
class SimpleOMSAdapter(OMSAdapter):
    """Simple OMS adapter that creates market orders."""

    def __init__(self, name: str = "SimpleOMSAdapter") -> None:
        super().__init__(name)

    async def create_order(
        self, 
        allocation_weights: AllocationWeights, 
        risk_metrics: RiskMetrics
    ) -> OrderEvent:
        """Create market orders based on allocation weights."""
        symbol, weight = self._get_highest_weight(allocation_weights)
        
        if symbol is None or weight <= Decimal('0'):
            return self._create_empty_order(allocation_weights.timestamp)
        
        # Determine side assuming long-only for Simple implementation
        side = "BUY"
        
        from qtrader.core.events import OrderPayload
        ts_val = int(allocation_weights.timestamp.timestamp() * 1_000_000)
        
        return OrderEvent(
            source="SimpleOMSAdapter",
            timestamp=ts_val,
            payload=OrderPayload(
                order_id=f"ORDER_{symbol}_{allocation_weights.timestamp.timestamp()}",
                symbol=symbol,
                action=side,
                quantity=weight,  # Using weight as simplified size
                order_type="MARKET",
                metadata={
                    "allocated_weight": float(weight),
                    "risk_metrics": {
                        "portfolio_var": float(risk_metrics.portfolio_var),
                        "portfolio_volatility": float(risk_metrics.portfolio_volatility),
                    }
                }
            )
        )

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders (simple implementation)."""
        self.logger.info("Cancelling all open orders (simple implementation)")
        # In a real implementation, we would call the OMS to cancel all orders
        pass


class ExecutionOMSAdapter(OMSAdapter):
    """OMS adapter that uses ExecutionEngine with smart routing to submit orders."""

    def __init__(
        self,
        exchange_adapters: dict[str, ExchangeAdapter],
        oms: UnifiedOMS,
        routing_mode: str = "smart",
        max_order_size: Decimal | None = None,
        split_size: Decimal | None = None,
        name: str = "ExecutionOMSAdapter",
    ) -> None:
        """
        Initialize ExecutionOMSAdapter.

        Args:
            exchange_adapters: Dictionary mapping exchange name to exchange adapter instance
            state_store: Centralized state store for order tracking
            routing_mode: Routing strategy ("best_price", "smart", "manual")
            max_order_size: Maximum order size for a single exchange (for splitting)
            split_size: Size of each split (if None, defaults to max_order_size)
            name: Name of this adapter
        """
        super().__init__(name)
        self.oms = oms
        self.exchange_adapters = exchange_adapters
        self.routing_mode = routing_mode
        self.max_order_size = max_order_size
        self.split_size = split_size

        # Create the smart router
        # Create the execution engine using the primary exchange adapter
        from qtrader.core.config import settings
        main_adapter = next(iter(exchange_adapters.values())) if exchange_adapters else None
        
        self.execution_engine = ExecutionEngine(
            exchange_adapter=main_adapter,
            max_orders_per_second=settings.ts_max_orders_per_second,
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
        symbol, weight = self._get_highest_weight(allocation_weights)

        if symbol is None or weight <= Decimal('0'):
            return self._create_empty_order(allocation_weights.timestamp)

        # Simple order sizing and side (assuming long-only)
        order_size = weight
        side = "BUY"

        # Create the OrderEvent
        from qtrader.core.events import OrderPayload
        ts_val = int(allocation_weights.timestamp.timestamp() * 1_000_000)
        
        order_event = OrderEvent(
            source="ExecutionOMSAdapter",
            timestamp=ts_val,
            payload=OrderPayload(
                order_id=f"ORDER_{symbol}_{allocation_weights.timestamp.timestamp()}",
                symbol=symbol,
                action=side,
                quantity=order_size,
                order_type="MARKET",
                metadata={
                    "allocated_weight": float(weight),
                    "risk_metrics": {
                        "portfolio_var": float(risk_metrics.portfolio_var),
                        "portfolio_volatility": float(risk_metrics.portfolio_volatility),
                    },
                    "_submitted_via_execution": True,
                }
            )
        )

        # [OMS_STATE_CENTRALIZATION]: Persist order to central OMS (delegated to Rust)
        await self.oms.create_order(order_event)

        self.logger.debug(f"Created order for {symbol}: weight={weight}, size={order_size}, side={side}")

        # Submit the order via the execution engine (non-blocking)
        asyncio.create_task(self._submit_order(order_event))

        return order_event

    async def _submit_order(self, order_event: OrderEvent) -> None:
        """Submit order via execution engine and log result."""
        try:
            order_id = order_event.payload.order_id
            self.logger.info(f"Submitting order {order_id} via execution engine")
            success, result = await self.execution_engine.execute_order(order_event)
            if success:
                await self.oms.on_ack(order_id)
                self.logger.info(f"Order {order_id} submitted successfully, result: {result}")
            else:
                await self.oms.on_reject(order_id, str(result))
                self.logger.warning(f"Order {order_id} submission failed: {result}")
        except Exception as e:
            oid = getattr(getattr(order_event, "payload", {}), "order_id", "unknown_oid")
            self.logger.error(f"Error submitting order {oid}: {e}", exc_info=True)
            # Standardize on REJECTED for failed submissions in Rust FSM
            await self.oms.on_reject(oid, f"Submission Error: {str(e)}")

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders via UnifiedOMS."""
        self.logger.info("Cancelling all open orders via ExecutionOMSAdapter")
        
        # Delegate to UnifiedOMS to ensure FSM and StateStore are synchronized
        active_orders = await self.oms.get_active_orders()
        for order_id in active_orders.keys():
            await self.oms.cancel_order(order_id)
            self.logger.info(f"Initiated cancellation for order: {order_id}")