import asyncio
import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from qtrader.core.config import settings
from qtrader.core.events import OrderPayload
from qtrader.core.execution_guard import require_initialized
from qtrader.core.logger import logger
from qtrader.core.types import AllocationWeights, OrderEvent, RiskMetrics
from qtrader.execution.execution_engine import ExchangeAdapter, ExecutionEngine
from qtrader.oms.order_management_system import UnifiedOMS


class OMSAdapter(ABC):
    def __init__(self, name: str = "OMSAdapter") -> None:
        self.name = name
        self.logger = logger
        self._tasks: set[asyncio.Task[Any]] = set()

    @require_initialized
    @abstractmethod
    async def create_order(
        self, allocation_weights: AllocationWeights, risk_metrics: RiskMetrics
    ) -> OrderEvent:
        pass

    @require_initialized
    @abstractmethod
    async def cancel_all_orders(self) -> None:
        pass

    def _get_highest_weight(
        self, allocation_weights: AllocationWeights
    ) -> tuple[str | None, Decimal]:
        symbol = None
        max_weight = Decimal("0")
        for sym, w in allocation_weights.weights.items():
            if w > max_weight:
                symbol = sym
                max_weight = w
        return (symbol, max_weight)

    def _create_empty_order(self, timestamp: Any) -> OrderEvent:
        ts_val = (
            int(timestamp.timestamp() * 1000000)
            if hasattr(timestamp, "timestamp")
            else int(time.time() * 1000000)
        )

        return OrderEvent(
            source="OMSAdapter",
            timestamp=ts_val,
            payload=OrderPayload(
                order_id="NO_TRADE",
                symbol="",
                action="BUY",
                quantity=Decimal("0"),
                order_type="MARKET",
                metadata={"reason": "no_allocation"},
            ),
        )


class SimpleOMSAdapter(OMSAdapter):
    def __init__(self, name: str = "SimpleOMSAdapter") -> None:
        super().__init__(name)

    async def create_order(
        self, allocation_weights: AllocationWeights, risk_metrics: RiskMetrics
    ) -> OrderEvent:
        (symbol, weight) = self._get_highest_weight(allocation_weights)
        if symbol is None or weight <= Decimal("0"):
            return self._create_empty_order(allocation_weights.timestamp)
        side = "BUY"

        ts_val = int(allocation_weights.timestamp.timestamp() * 1000000)
        return OrderEvent(
            source="SimpleOMSAdapter",
            timestamp=ts_val,
            payload=OrderPayload(
                order_id=f"ORDER_{symbol}_{allocation_weights.timestamp.timestamp()}",
                symbol=symbol,
                action=side,
                quantity=weight,
                order_type="MARKET",
                metadata={
                    "allocated_weight": float(weight),
                    "risk_metrics": {
                        "portfolio_var": float(risk_metrics.portfolio_var),
                        "portfolio_volatility": float(risk_metrics.portfolio_volatility),
                    },
                },
            ),
        )

    async def cancel_all_orders(self) -> None:
        self.logger.info("Cancelling all open orders (simple implementation)")


class ExecutionOMSAdapter(OMSAdapter):
    def __init__(
        self,
        exchange_adapters: dict[str, ExchangeAdapter],
        oms: UnifiedOMS,
        routing_mode: str = "smart",
        max_order_size: Decimal | None = None,
        split_size: Decimal | None = None,
        name: str = "ExecutionOMSAdapter",
    ) -> None:
        super().__init__(name)
        self.oms = oms
        self.exchange_adapters = exchange_adapters
        self.routing_mode = routing_mode
        self.max_order_size = max_order_size
        self.split_size = split_size

        main_adapter = next(iter(exchange_adapters.values())) if exchange_adapters else None
        self.execution_engine = ExecutionEngine(
            exchange_adapter=main_adapter,
            max_orders_per_second=settings.ts_max_orders_per_second,
            logger=self.logger,
        )
        self._engine_started = False
        self.logger.info(f"ExecutionOMSAdapter initialized with {len(exchange_adapters)} exchanges")

    async def start(self) -> None:
        if not self._engine_started:
            await self.execution_engine.start()
            self._engine_started = True
            self.logger.info("ExecutionOMSAdapter execution engine started")

    async def stop(self) -> None:
        if self._engine_started:
            await self.execution_engine.stop()
            self._engine_started = False
            self.logger.info("ExecutionOMSAdapter execution engine stopped")

    async def create_order(
        self, allocation_weights: AllocationWeights, risk_metrics: RiskMetrics
    ) -> OrderEvent:
        if not self._engine_started:
            await self.start()
        (symbol, weight) = self._get_highest_weight(allocation_weights)
        if symbol is None or weight <= Decimal("0"):
            return self._create_empty_order(allocation_weights.timestamp)
        order_size = weight
        side = "BUY"

        ts_val = int(allocation_weights.timestamp.timestamp() * 1000000)
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
                },
            ),
        )
        await self.oms.create_order(order_event)
        self.logger.debug(
            f"Created order for {symbol}: weight={weight}, size={order_size}, side={side}"
        )
        task = asyncio.create_task(self._submit_order(order_event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return order_event

    async def _submit_order(self, order_event: OrderEvent) -> None:
        try:
            order_id = order_event.payload.order_id
            self.logger.info(f"Submitting order {order_id} via execution engine")
            (success, result) = await self.execution_engine.execute_order(order_event)
            if success:
                await self.oms.on_ack(order_id)
                self.logger.info(f"Order {order_id} submitted successfully, result: {result}")
            else:
                await self.oms.on_reject(order_id, str(result))
                self.logger.warning(f"Order {order_id} submission failed: {result}")
        except Exception as e:
            oid = getattr(getattr(order_event, "payload", {}), "order_id", "unknown_oid")
            self.logger.error(f"Error submitting order {oid}: {e}", exc_info=True)
            await self.oms.on_reject(oid, f"Submission Error: {e!s}")

    async def cancel_all_orders(self) -> None:
        self.logger.info("Cancelling all open orders via ExecutionOMSAdapter")
        active_orders = await self.oms.state_store.get_active_orders()
        for order_id in active_orders.keys():
            await self.oms.cancel_order(order_id)
            self.logger.info(f"Initiated cancellation for order: {order_id}")
