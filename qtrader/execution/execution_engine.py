# File: qtrader/execution/execution_engine.py
from __future__ import annotations

import asyncio
import queue
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from qtrader_core import (
    ExecutionEngine as RustExecutionEngine,
)
from qtrader_core import (
    Order as RustOrder,
)
from qtrader_core import (
    OrderType as RustOrderType,
)
from qtrader_core import (
    RiskEngine as RustRiskEngine,
)
from qtrader_core import (
    RoutingMode as RustRoutingMode,
)
from qtrader_core import (
    Side as RustSide,
)

from qtrader.core.events import FillEvent, FillPayload, OrderEvent
from qtrader.core.logger import logger
from qtrader.core.state_store import Position, StateStore
from qtrader.core.trace_authority import TraceAuthority
from qtrader.core.types import LoggerProtocol
from qtrader.risk.kill_switch import GlobalKillSwitch
from qtrader.risk.war_mode import WarModeEngine

from .orderbook_simulator import OrderbookSimulator
from .rate_limiter import TokenBucketRateLimiter


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExchangeAdapter(ABC):
    def __init__(self, name: str, logger: LoggerProtocol = logger) -> None:
        self.name = name
        self.logger = logger

    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> str:
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Decimal:
        pass

    async def get_positions(self) -> dict[str, Decimal]:
        return {}

    async def get_orderbook(self, symbol: str) -> dict[str, Any]:
        return {}

    async def get_fees(self, symbol: str) -> dict[str, Decimal]:
        return {}


class SimulatedExchangeAdapter(ExchangeAdapter):
    def __init__(
        self,
        name: str = "SimulatedExchange",
        logger: LoggerProtocol = logger,
        kill_switch: GlobalKillSwitch | None = None,
    ) -> None:
        super().__init__(name, logger)
        self.kill_switch = kill_switch
        # Simulated market data: symbol -> price
        self.prices: dict[str, Decimal] = {}
        # Simulated positions: symbol -> quantity
        self.positions: dict[str, Decimal] = {}
        # Simulated orders: order_id -> order details
        self.orders: dict[str, dict[str, Any]] = {}
        # Order ID counter
        self.order_counter = 0
        # Orderbook simulator for realistic execution simulation
        self.orderbook: dict[str, list[tuple[float, float]]] | None = None
        self.orderbook_simulator = OrderbookSimulator(
            latency_ms=0.0, market_impact_k=0.1, max_slippage_pct=0.01
        )
        self._fill_callback = None  # Optional callback for fill events

    def set_price(self, symbol: str, price: Decimal) -> None:
        self.prices[symbol] = price

    def set_fill_callback(self, callback) -> None:
        self._fill_callback = callback

    async def _async_notify_fill(self, order_id: str, fill_event: FillEvent) -> None:
        if self._fill_callback:
            self._fill_callback(order_id, fill_event)

    async def submit_order(self, order: OrderEvent) -> str:
        try:
            self.order_counter += 1
            order_id = f"SIM_{self.order_counter}_{int(time.time() * 1000)}"
            self.orders[order_id] = {
                "order": order,
                "status": OrderStatus.OPEN,
                "timestamp": datetime.utcnow(),
                "filled_size": Decimal("0"),
                "avg_price": Decimal("0"),
            }
            self.logger.info(
                f"Simulated exchange: Order submitted - ID: {order_id}, Symbol: {order.payload.symbol}, Side: {order.payload.action}, Quantity: {order.payload.quantity}, Price: {order.payload.price}"
            )
            if order.payload.order_type == "MARKET":
                if order.payload.symbol in self.prices:
                    fill_price = self.prices[order.payload.symbol]
                    self.orders[order_id]["status"] = OrderStatus.FILLED
                    self.orders[order_id]["filled_size"] = order.payload.quantity
                    self.orders[order_id]["avg_price"] = fill_price
            return order_id
        except Exception as e:
            self.logger.error(f"Simulated exchange submission error: {e}", exc_info=True)
            raise

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        if order_id not in self.orders:
            return False, f"Order ID {order_id} not found"

        order_info = self.orders[order_id]
        if order_info["status"] in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False, f"Order {order_id} is already {order_info['status'].value}"

        order_info["status"] = OrderStatus.CANCELLED
        self.logger.info(f"Simulated exchange: Order cancelled - ID: {order_id}")
        return True, None

    async def get_position(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal("0"))

    def check_and_fill_limit_orders(self, current_prices: dict[str, Decimal]) -> list:
        fills = []
        for order_id, order_info in self.orders.items():
            if order_info["status"] != OrderStatus.OPEN:
                continue

            order = order_info["order"]
            symbol = order.payload.symbol

            if symbol not in current_prices:
                continue

            price = current_prices[symbol]
            side = order.payload.action
            limit_price = order.payload.price

            if limit_price is None:
                continue

            can_fill = (side == "BUY" and price <= limit_price) or (
                side == "SELL" and price >= limit_price
            )
            if can_fill:
                fill_event = FillEvent(
                    source="SimulatedExchange",
                    payload=FillPayload(
                        order_id=order_id,
                        symbol=symbol,
                        side=side,
                        quantity=order.payload.quantity,
                        price=price,
                        commission=Decimal("0.0"),
                    ),
                )
                fills.append(fill_event)
                order_info["status"] = OrderStatus.FILLED
                order_info["filled_size"] = order.payload.quantity
                order_info["avg_price"] = price

        return fills


class ExecutionEngine:
    def __init__(
        self,
        exchange_adapter: ExchangeAdapter,
        state_store: StateStore | None = None,
        max_order_size: float = 1000000.0,  # Default max order size in quote currency
        max_slippage: float = 0.01,  # 1% max slippage for market orders
        max_retry_attempts: int = 3,
        max_orders_per_second: float = 10.0,
        retry_delay_base: float = 0.1,  # Base delay in seconds for exponential backoff
        enable_failover_queue: bool = True,
        event_bus: Any | None = None,
        logger: LoggerProtocol = logger,
        war_mode: WarModeEngine | None = None,
    ) -> None:
        self.exchange_adapter = exchange_adapter
        self.state_store = state_store or StateStore()

        # === RUST EXECUTION CORE INITIALIZATION (Standash §2) ===
        # Create a Rust RiskEngine with matching limits (Required for WarModeEngine)
        self._rust_risk = RustRiskEngine(
            max_position_usd=max_order_size,  # Simplified mapping
            max_drawdown_pct=0.1,  # Default 10%
            max_order_notional=max_order_size,
        )

        self.war_mode = war_mode or WarModeEngine(rust_engine=self._rust_risk)

        # If the adapter supports fill callback, set it
        if hasattr(exchange_adapter, "set_fill_callback"):
            exchange_adapter.set_fill_callback(self._on_order_filled)
        self.max_order_size = max_order_size
        self.max_slippage = max_slippage
        self.max_retry_attempts = max_retry_attempts
        self.retry_delay_base = retry_delay_base
        self.enable_failover_queue = enable_failover_queue
        self.logger = logger
        self._event_bus = event_bus

        # Python-side Rate Limiter (Standash §6.1)
        self.rate_limiter = TokenBucketRateLimiter(
            capacity=max_orders_per_second, refill_rate=max_orders_per_second
        )

        # Background Execution Worker (Hybrid Concurrency)
        self._worker_queue: queue.Queue = queue.Queue()
        self._rust_engine: RustExecutionEngine | None = None
        self._max_retry_attempts = max_retry_attempts
        self._worker_thread = threading.Thread(
            target=self._execution_worker_loop, daemon=True, name="ExecutionWorker"
        )

        # Subscribe to retries if event bus is available
        if self._event_bus:
            from qtrader.core.events import EventType

            self._event_bus.subscribe(EventType.RETRY_ORDER, self._on_retry_order)

        self._is_running = False

    async def start(self) -> None:
        if self._is_running:
            return

        self._is_running = True
        self._worker_thread.start()
        self.logger.info("ExecutionEngine started (with Rust Worker Thread)")

    async def stop(self) -> None:
        self._is_running = False
        self._worker_queue.put(None)  # Signal worker to stop
        self._worker_thread.join(timeout=2.0)
        self.logger.info("ExecutionEngine stopped")

    from qtrader.core.latency import enforce_latency

    @enforce_latency(threshold_ms=2.0)
    async def execute_order(self, order: OrderEvent, attempt: int = 1) -> tuple[bool, str | None]:
        if not self.rate_limiter.consume():
            self.logger.warning(f"Rate limit exceeded for {order.symbol}, deferring...")
            await self.rate_limiter.wait_and_consume()

        # 2. Prepare Task for Rust Worker
        future = asyncio.get_event_loop().create_future()
        task = ("EXECUTE", order, future)
        self._worker_queue.put(task)

        # 3. Wait for Worker Result
        try:
            routed_orders = await future

            # 4. Dispatch the routed orders back to Python adapters
            all_success = True
            last_id = None

            for r_order, exchange in routed_orders:
                from qtrader.core.events import OrderPayload

                dispatch_order = OrderEvent(
                    source="ExecutionEngine",
                    timestamp=int(time.time() * 1_000_000),
                    payload=OrderPayload(
                        order_id=f"{exchange}_{r_order.id}",
                        symbol=r_order.symbol,
                        action="BUY" if r_order.side == RustSide.Buy else "SELL",
                        quantity=Decimal(str(r_order.qty)),
                        price=Decimal(str(r_order.price)) if r_order.price > 0 else None,
                        order_type="MARKET"
                        if r_order.order_type == RustOrderType.Market
                        else "LIMIT",
                        metadata={**(order.payload.metadata or {}), "exchange": exchange},
                    ),
                )

                try:
                    broker_oid = await self.exchange_adapter.submit_order(dispatch_order)
                    last_id = broker_oid
                except Exception as e:
                    self.logger.error(f"Failed to submit order to {exchange}: {e}")
                    all_success = False
                    last_id = str(e)
                    break  # Stop dispatching subsequent legs if one fails

            return all_success, last_id

        except Exception as e:
            self.logger.error(f"Execution failure: {e}", exc_info=True)
            return False, str(e)

    async def _on_retry_order(self, event: Any) -> None:
        from qtrader.core.events import RetryOrderEvent

        if isinstance(event, RetryOrderEvent):
            await self.execute_order(event.order, attempt=event.attempt)

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        return await self.exchange_adapter.cancel_order(order_id)

    def _validate_order(self, order: OrderEvent) -> str | None:
        if order.quantity <= 0:
            return "Order quantity must be positive"

        # Check max order size (in quote currency, approximate)
        # We need a price to calculate quote size; if not available, skip this check for now
        if order.price is not None:
            quote_size = order.quantity * order.price
            if quote_size > self.max_order_size:
                return f"Order quote size {quote_size} exceeds maximum {self.max_order_size}"

        # Check order type specific validations
        if order.order_type == OrderType.LIMIT.value and order.price is None:
            return "Limit order must have a price"

        if order.order_type == OrderType.MARKET.value and order.price is not None:
            self.logger.warning("Market order received with price; price will be ignored")

        # Additional safety checks could be added here (e.g., symbol validation, etc.)

        return None

    def _execution_worker_loop(self) -> None:
        # Safely retrieve simulation parameters from adapter defaults if available
        latency = 0.0
        slippage = float(self.max_slippage * 10000)  # Default from engine config

        if hasattr(self.exchange_adapter, "orderbook_simulator"):
            latency = self.exchange_adapter.orderbook_simulator.latency_ms
            slippage = float(self.exchange_adapter.orderbook_simulator.max_slippage_pct * 10000)

        self._rust_engine = RustExecutionEngine(
            risk_engine=self._rust_risk,
            initial_capital=1000000.0,
            routing_mode=RustRoutingMode.Smart,
            max_retries=self._max_retry_attempts,
            latency_ms=latency,
            slippage_bps=slippage,
        )
        loop = asyncio.new_event_loop()  # For future completion if needed
        # Standash §4.2: Suppress trace warnings in background worker using TraceAuthority
        with TraceAuthority.inject_trace("EXEC_WORKER_THREAD"):
            while True:
                try:
                    item = self._worker_queue.get()
                    if item is None:
                        break

                    cmd, data, future = item

                    if cmd == "EXECUTE":
                        order = data
                        # Map to Rust using payload (Standash §2)
                        rust_side = RustSide.Buy if order.payload.action == "BUY" else RustSide.Sell
                        rust_type = (
                            RustOrderType.Market
                            if order.payload.order_type == "MARKET"
                            else RustOrderType.Limit
                        )
                        rust_order = RustOrder(
                            id=str(int(time.time() * 1000)),
                            symbol=order.payload.symbol,
                            side=rust_side,
                            qty=float(order.payload.quantity),
                            price=float(order.payload.price) if order.payload.price else 0.0,
                            order_type=rust_type,
                            timestamp_ms=int(time.time() * 1000),
                        )

                        market_data = {order.payload.symbol: (100.0, 100.1)}  # Simplified

                        try:
                            result = self._rust_engine.execute_order(
                                rust_order,
                                1000000.0,  # Peak equity placeholder
                                market_data,
                            )
                            future.get_loop().call_soon_threadsafe(future.set_result, result)
                        except Exception as e:
                            future.get_loop().call_soon_threadsafe(future.set_exception, e)

                    elif cmd == "FILL_UPDATE":
                        fill_event = data
                        rust_side = (
                            RustSide.Buy if fill_event.payload.side == "BUY" else RustSide.Sell
                        )
                        self._rust_engine.update_fill(
                            fill_event.payload.symbol,
                            rust_side,
                            float(fill_event.payload.quantity),
                            float(fill_event.payload.price),
                        )

                except Exception as e:
                    self.logger.error(f"ExecutionWorker Error: {e}")
                finally:
                    self._worker_queue.task_done()

    # Methods to be called by the exchange adapter or market data feed to update order status
    def _on_order_filled(self, order_id: str, fill_event: FillEvent) -> None:
        # 1. Sync Rust state via background worker
        self._worker_queue.put(("FILL_UPDATE", fill_event, None))

        # 2. Propagation & Logging
        from qtrader.execution.trade_logger import TradeLogger

        trace_id = getattr(
            fill_event,
            "trace_id",
            getattr(fill_event.payload, "metadata", {}).get("trace_id", "no_trace"),
        )
        metadata = getattr(fill_event.payload, "metadata", {})
        TradeLogger.log_trade(
            symbol=fill_event.payload.symbol,
            side=fill_event.payload.side,
            quantity=float(fill_event.payload.quantity),
            price=float(fill_event.payload.price),
            trace_id=str(trace_id),
            timestamp=getattr(fill_event, "timestamp", time.time()),
            sl=float(metadata.get("sl", 0.0)),
            tp=float(metadata.get("tp", 0.0)),
            reason=metadata.get("reason", "SIGNAL"),
        )

        self._log_explainability(fill_event, trace_id)

    def _log_explainability(self, fill_event: FillEvent, trace_id: str) -> None:
        try:
            # Extract decision metadata from fill event payload
            metadata = getattr(fill_event.payload, "metadata", {})
            explanation = metadata.get("explanation", "No explanation available")
            reasoning = metadata.get("reasoning", "No reasoning available")
            ml_confidence = metadata.get("confidence", 0.0)
            ml_signal = metadata.get("ml_signal", "UNKNOWN")

            self.logger.info(
                f"[ML_TRACE] {trace_id} | Signal: {ml_signal} (Conf: {ml_confidence:.2f}) | Logic: {explanation}"
            )
        except Exception as e:
            self.logger.debug(f"[EXPLAINABILITY] Failed to log explainability: {e}")

    def _on_order_cancelled(self, order_id: str) -> None:
        self.logger.info(f"Order cancelled: {order_id}")

    async def _update_position_from_fill(self, fill_event: FillEvent) -> None:
        symbol = fill_event.payload.symbol
        quantity = (
            fill_event.payload.quantity
            if fill_event.payload.side == "BUY"
            else -fill_event.payload.quantity
        )

        current = await self.state_store.get_position(symbol)
        if current:
            new_qty = current.quantity + quantity
            new_cost = (current.quantity * current.average_price) + (
                fill_event.payload.quantity * fill_event.payload.price
            )
            new_avg = new_cost / new_qty if new_qty != 0 else Decimal("0")
            await self.state_store.set_position(
                Position(
                    symbol=symbol,
                    quantity=new_qty,
                    average_price=new_avg,
                    timestamp=datetime.utcnow(),
                )
            )
        else:
            await self.state_store.set_position(
                Position(
                    symbol=symbol,
                    quantity=quantity,
                    average_price=fill_event.payload.price,
                    timestamp=datetime.utcnow(),
                )
            )

    async def get_position(self, symbol: str) -> Decimal:
        pos = await self.state_store.get_position(symbol)
        return pos.quantity if pos else Decimal("0")

    async def get_average_price(self, symbol: str) -> Decimal | None:
        pos = await self.state_store.get_position(symbol)
        return pos.average_price if pos else None


# Example usage (not part of the required output, but for illustration)
if __name__ == "__main__":
    # This is just for demonstration; normally this would be used by the orchestrator
    pass
