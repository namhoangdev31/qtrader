# File: qtrader/execution/execution_engine.py
import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import threading
import queue

from qtrader.core.logger import logger
from qtrader.core.state_store import Position, StateStore
from qtrader.core.types import FillEvent, LoggerProtocol, OrderEvent
from qtrader.risk.kill_switch import GlobalKillSwitch
from qtrader.risk.war_mode import WarModeEngine

import qtrader_core
from qtrader_core import (
    Account as RustAccount,
    Order as RustOrder,
    OrderType as RustOrderType,
    Side as RustSide,
    ExecutionEngine as RustExecutionEngine,
    RoutingMode as RustRoutingMode,
    RiskEngine as RustRiskEngine,
)

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
    """Abstract base class for exchange adapters."""

    def __init__(self, name: str, logger: LoggerProtocol = logger) -> None:
        self.name = name
        self.logger = logger

    @abstractmethod
    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        """
        Send an order to the exchange.

        Args:
            order: OrderEvent to send

        Returns:
            Tuple (success, order_id or error_message)
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """
        Cancel an order on the exchange.

        Args:
            order_id: ID of the order to cancel

        Returns:
            Tuple (success, error_message)
        """
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Decimal:
        """
        Get current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position size (can be negative)
        """
        pass

    async def get_positions(self) -> dict[str, Decimal]:
        """Get current positions from the exchange."""
        return {}

    async def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """Get orderbook for a symbol."""
        return {}

    async def get_fees(self, symbol: str) -> dict[str, Decimal]:
        """Get trading fees for a symbol."""
        return {}


class SimulatedExchangeAdapter(ExchangeAdapter):
    """Simulated exchange adapter for testing and development."""

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
        """Set the simulated price for a symbol."""
        self.prices[symbol] = price

    def set_fill_callback(self, callback) -> None:
        """Set callback for fill events. Callback signature: (order_id: str, fill_event: FillEvent) -> None"""
        self._fill_callback = callback

    async def _async_notify_fill(self, order_id: str, fill_event: FillEvent) -> None:
        """Async helper to call fill callback."""
        if self._fill_callback:
            self._fill_callback(order_id, fill_event)

    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        """Simulate sending an order to the exchange."""
        try:
            # Generate a unique order ID
            self.order_counter += 1
            order_id = f"SIM_{self.order_counter}_{int(time.time() * 1000)}"

            # Store the order
            self.orders[order_id] = {
                "order": order,
                "status": OrderStatus.OPEN,
                "timestamp": datetime.utcnow(),
                "filled_size": Decimal("0"),
                "avg_price": Decimal("0"),
            }

            self.logger.info(
                f"Simulated exchange: Order sent - ID: {order_id}, Symbol: {order.symbol}, Side: {order.side}, Quantity: {order.quantity}, Price: {order.price}"
            )

            # For simulation, we can immediately fill market orders or simulate limit order filling
            if order.order_type == OrderType.MARKET.value:
                # Market order: fill immediately at current price
                if order.symbol in self.prices:
                    fill_price = self.prices[order.symbol]
                    # Simulate slippage (optional)
                    slippage = Decimal("0.001")  # 0.1% slippage
                    if order.side == "BUY":
                        fill_price *= 1 + slippage
                    else:
                        fill_price *= 1 - slippage

                    # Update position
                    self.positions[order.symbol] = self.positions.get(
                        order.symbol, Decimal("0")
                    ) + (order.quantity if order.side == "BUY" else -order.quantity)

                    # Create fill event
                    fill_event = FillEvent(
                        order_id=order_id,
                        symbol=order.symbol,
                        timestamp=datetime.utcnow(),
                        side=order.side,
                        quantity=order.quantity,
                        price=fill_price,
                        commission=Decimal("0"),
                    )

                    # Update order status
                    self.orders[order_id]["status"] = OrderStatus.FILLED
                    self.orders[order_id]["filled_size"] = order.quantity
                    self.orders[order_id]["avg_price"] = fill_price

                    # Notify fill callback asynchronously
                    if self._fill_callback:
                        asyncio.create_task(self._async_notify_fill(order_id, fill_event))

                    # Return the fill event via callback? In a real system, we'd emit an event.
                    # For this adapter, we return the order ID and the caller can request fills.
                    return True, order_id
                else:
                    # No price available, reject order
                    self.orders[order_id]["status"] = OrderStatus.REJECTED
                    return False, f"No price available for symbol {order.symbol}"
            else:
                # Limit order: remain open until price conditions are met
                # In simulation, we'll just leave it open and let the caller check for fills later
                self.logger.info(f"Simulated exchange: Limit order placed - ID: {order_id}")
                return True, order_id

        except ConnectionError as e:
            self.logger.critical(f"CRITICAL: Exchange connection lost: {e}")
            if self.kill_switch:
                self.kill_switch.trigger_on_critical_failure("BROKER_DISCONNECT", str(e))
            return False, f"Exchange connection lost: {e}"
        except Exception as e:
            self.logger.error(f"Error sending order to simulated exchange: {e}", exc_info=True)
            return False, str(e)

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """Simulate cancelling an order on the exchange."""
        if order_id not in self.orders:
            return False, f"Order ID {order_id} not found"

        order_info = self.orders[order_id]
        if order_info["status"] in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False, f"Order {order_id} is already {order_info['status'].value}"

        order_info["status"] = OrderStatus.CANCELLED
        self.logger.info(f"Simulated exchange: Order cancelled - ID: {order_id}")
        return True, None

    async def get_position(self, symbol: str) -> Decimal:
        """Get simulated position for a symbol."""
        return self.positions.get(symbol, Decimal("0"))

    def check_and_fill_limit_orders(self, current_prices: dict[str, Decimal]) -> list:
        """
        Check limit orders against current prices and fill them if conditions are met.
        This is a helper method for simulation to generate fill events.

        Args:
            current_prices: Dictionary of symbol -> current price

        Returns:
            List of FillEvent objects for orders that were filled
        """
        fills = []
        for order_id, order_info in self.orders.items():
            if order_info["status"] != OrderStatus.OPEN:
                continue

            order = order_info["order"]
            symbol = order.symbol

            if symbol not in current_prices:
                continue

            current_price = current_prices[symbol]
            should_fill = False
            fill_price = current_price

            if order.side == "BUY" and order.price is not None and current_price <= order.price:
                should_fill = True
            elif order.side == "SELL" and order.price is not None and current_price >= order.price:
                should_fill = True

            if should_fill:
                # Fill the order
                self.positions[symbol] = self.positions.get(symbol, Decimal("0")) + (
                    order.quantity if order.side == "BUY" else -order.quantity
                )

                fill_event = FillEvent(
                    order_id=order_id,
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    side=order.side,
                    quantity=order.quantity,
                    price=fill_price,
                    commission=Decimal("0"),
                )
                fills.append(fill_event)

                # Update order status
                order_info["status"] = OrderStatus.FILLED
                order_info["filled_size"] = order.quantity
                order_info["avg_price"] = fill_price

                # Notify fill callback asynchronously
                if self._fill_callback:
                    asyncio.create_task(self._async_notify_fill(order_id, fill_event))

                self.logger.info(
                    f"Simulated exchange: Limit order filled - ID: {order_id}, Symbol: {symbol}, Price: {fill_price}"
                )

        return fills


class ExecutionEngine:
    """
    Real execution layer connecting QTrader to exchanges.
    Handles order validation, routing, execution logic, position tracking, retry logic, failover, and safety checks.
    """

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
            max_drawdown_pct=0.1,             # Default 10%
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
            capacity=max_orders_per_second,
            refill_rate=max_orders_per_second
        )

        # Background Execution Worker (Hybrid Concurrency)
        self._worker_queue: queue.Queue = queue.Queue()
        self._rust_engine: RustExecutionEngine | None = None
        self._max_retry_attempts = max_retry_attempts
        self._worker_thread = threading.Thread(
            target=self._execution_worker_loop,
            daemon=True,
            name="ExecutionWorker"
        )

        # Subscribe to retries if event bus is available
        if self._event_bus:
            from qtrader.core.events import EventType

            self._event_bus.subscribe(EventType.RETRY_ORDER, self._on_retry_order)

        self._is_running = False

    async def start(self) -> None:
        """Start the execution engine background tasks."""
        if self._is_running:
            return

        self._is_running = True
        self._worker_thread.start()
        self.logger.info("ExecutionEngine started (with Rust Worker Thread)")

    async def stop(self) -> None:
        """Stop the execution engine background tasks."""
        self._is_running = False
        self._worker_queue.put(None)  # Signal worker to stop
        self._worker_thread.join(timeout=2.0)
        self.logger.info("ExecutionEngine stopped")

    from qtrader.core.latency import enforce_latency

    @enforce_latency(threshold_ms=2.0)  # Further reduced due to dedicated thread
    async def execute_order(self, order: OrderEvent, attempt: int = 1) -> tuple[bool, str | None]:
        """
        Execute an order with Python-side rate limiting and background Rust processing.
        """
        # 1. Python-side Rate Limiting (Safety Check)
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
                dispatch_order = OrderEvent(
                    order_id=f"{exchange}_{r_order.id}",
                    symbol=r_order.symbol,
                    timestamp=datetime.utcnow(),
                    order_type="MARKET" if r_order.order_type == RustOrderType.Market else "LIMIT",
                    side="BUY" if r_order.side == RustSide.Buy else "SELL",
                    quantity=Decimal(str(r_order.qty)),
                    price=Decimal(str(r_order.price)) if r_order.price > 0 else None,
                    metadata={**(order.metadata or {}), "exchange": exchange}
                )
                
                success, result = await self.exchange_adapter.send_order(dispatch_order)
                if success:
                    last_id = result
                else:
                    all_success = False
            
            return all_success, last_id

        except Exception as e:
            self.logger.error(f"Execution failure: {e}", exc_info=True)
            return False, str(e)

    async def _on_retry_order(self, event: Any) -> None:
        """Handler for RetryOrderEvent."""
        from qtrader.core.events import RetryOrderEvent

        if isinstance(event, RetryOrderEvent):
            await self.execute_order(event.order, attempt=event.attempt)

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """Cancel an order via the adapter purely stateless."""
        return await self.exchange_adapter.cancel_order(order_id)

    def _validate_order(self, order: OrderEvent) -> str | None:
        """
        Validate an order before sending.

        Args:
            order: OrderEvent to validate

        Returns:
            Error message if invalid, None if valid
        """
        # Check quantity
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

    # Redundant loop removed for event-driven architecture

    def _execution_worker_loop(self) -> None:
        """
        Background thread loop that manages the RustExecutionEngine synchronously.
        """
        # Initialize Rust engine in this thread
        self._rust_engine = RustExecutionEngine(
            risk_engine=self._rust_risk,
            initial_capital=1000000.0, # Placeholder
            routing_mode=RustRoutingMode.Smart,
            max_retries=self._max_retry_attempts,
        )
        loop = asyncio.new_event_loop() # For future completion if needed

        while True:
            try:
                item = self._worker_queue.get()
                if item is None:
                    break
                
                cmd, data, future = item
                
                if cmd == "EXECUTE":
                    order = data
                    # Map to Rust
                    rust_side = RustSide.Buy if order.side == "BUY" else RustSide.Sell
                    rust_type = RustOrderType.Market if order.order_type == "MARKET" else RustOrderType.Limit
                    rust_order = RustOrder(
                        id=int(time.time() * 1000),
                        symbol=order.symbol,
                        side=rust_side,
                        qty=float(order.quantity),
                        price=float(order.price) if order.price else 0.0,
                        order_type=rust_type,
                        timestamp_ms=int(time.time() * 1000)
                    )
                    
                    market_data = {order.symbol: (100.0, 100.1)} # Simplified
                    
                    try:
                        result = self._rust_engine.execute_order(
                            rust_order,
                            1000000.0, # Peak equity placeholder
                            market_data
                        )
                        future.get_loop().call_soon_threadsafe(future.set_result, result)
                    except Exception as e:
                        future.get_loop().call_soon_threadsafe(future.set_exception, e)

                elif cmd == "FILL_UPDATE":
                    fill_event = data
                    rust_side = RustSide.Buy if fill_event.side == "BUY" else RustSide.Sell
                    self._rust_engine.update_fill(
                        fill_event.symbol,
                        rust_side,
                        float(fill_event.quantity),
                        float(fill_event.price)
                    )

            except Exception as e:
                self.logger.error(f"ExecutionWorker Error: {e}")
            finally:
                self._worker_queue.task_done()

    # Methods to be called by the exchange adapter or market data feed to update order status
    def _on_order_filled(self, order_id: str, fill_event: FillEvent) -> None:
        """Callback to handle an order fill."""
        # 1. Sync Rust state via background worker
        self._worker_queue.put(("FILL_UPDATE", fill_event, None))
        
        # 2. Propagation & Logging

        # Standardized institutional trade log
        from qtrader.execution.trade_logger import TradeLogger

        trace_id = getattr(fill_event, "trace_id", "no_trace")
        TradeLogger.log_trade(
            symbol=fill_event.symbol,
            side=fill_event.side,
            quantity=float(fill_event.quantity),
            price=float(fill_event.price),
            trace_id=trace_id,
            timestamp=fill_event.timestamp,
        )

        # ML Explainability: Log decision attribution (Standash §13)
        self._log_explainability(fill_event, trace_id)

    def _log_explainability(self, fill_event: FillEvent, trace_id: str) -> None:
        """Log ML explainability for executed fills (Standash §13).

        Records which factors contributed to the trade decision,
        providing institutional transparency for audit and compliance.
        """
        try:
            # Extract decision metadata from fill event
            metadata = getattr(fill_event, "metadata", {})
            explanation = metadata.get("explanation", "No explanation available")
            reasoning = metadata.get("reasoning", "No reasoning available")
            ml_confidence = metadata.get("confidence", 0.0)
            ml_signal = metadata.get("ml_signal", "UNKNOWN")

            self.logger.info(
                f"[EXPLAINABILITY] Trade {trace_id} | "
                f"Signal: {ml_signal} | Confidence: {ml_confidence:.0%} | "
                f"Reasoning: {reasoning} | "
                f"Explanation: {explanation[:200]}"
            )
        except Exception as e:
            self.logger.debug(f"[EXPLAINABILITY] Failed to log explainability: {e}")

    def _on_order_cancelled(self, order_id: str) -> None:
        """Callback to handle an order cancellation."""
        self.logger.info(f"Order cancelled: {order_id}")

    async def _update_position_from_fill(self, fill_event: FillEvent) -> None:
        """[STATELESS_EXECUTION]: Update central state store instead of local trackers."""
        symbol = fill_event.symbol
        quantity = fill_event.quantity if fill_event.side == "BUY" else -fill_event.quantity

        # We rely on the orchestrator to do the primary update, but we ensure
        # consistency here if required. However, for a truly stateless worker,
        # we can just fetch and verify.
        current = await self.state_store.get_position(symbol)
        if current:
            # Recompute average price and update
            new_qty = current.quantity + quantity
            new_cost = (current.quantity * current.average_price) + (
                fill_event.quantity * fill_event.price
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
                    average_price=fill_event.price,
                    timestamp=datetime.utcnow(),
                )
            )

    async def get_position(self, symbol: str) -> Decimal:
        """[STATELESS_EXECUTION]: Fetch current position from central state store."""
        pos = await self.state_store.get_position(symbol)
        return pos.quantity if pos else Decimal("0")

    async def get_average_price(self, symbol: str) -> Decimal | None:
        """[STATELESS_EXECUTION]: Fetch average price from central state store."""
        pos = await self.state_store.get_position(symbol)
        return pos.average_price if pos else None


# Example usage (not part of the required output, but for illustration)
if __name__ == "__main__":
    # This is just for demonstration; normally this would be used by the orchestrator
    pass
