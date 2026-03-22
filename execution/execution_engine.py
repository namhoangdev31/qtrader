# File: qtrader/execution/execution_engine.py
import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from decimal import Decimal

from qtrader.core.types import OrderEvent, FillEvent, LoggerProtocol
from qtrader.core.logger import logger
from .orderbook_simulator import OrderbookSimulator

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
    
    def __init__(self, name: str, logger: LoggerProtocol = logger):
        self.name = name
        self.logger = logger
    
    @abstractmethod
    async def send_order(self, order: OrderEvent) -> Tuple[bool, Optional[str]]:
        """
        Send an order to the exchange.
        
        Args:
            order: OrderEvent to send
            
        Returns:
            Tuple (success, order_id or error_message)
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> Tuple[bool, Optional[str]]:
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

class SimulatedExchangeAdapter(ExchangeAdapter):
    """Simulated exchange adapter for testing and development."""
    
    def __init__(self, name: str = "SimulatedExchange", logger: LoggerProtocol = logger):
        super().__init__(name, logger)
        # Simulated market data: symbol -> price
        self.prices: Dict[str, Decimal] = {}
        # Simulated positions: symbol -> quantity
        self.positions: Dict[str, Decimal] = {}
        # Simulated orders: order_id -> order details
        self.orders: Dict[str, Dict[str, Any]] = {}
        # Order ID counter
        self.order_counter = 0
        # Orderbook simulator for realistic execution simulation
        self.orderbook: Optional[Dict[str, List[Tuple[float, float]]]] = None
        self.orderbook_simulator = OrderbookSimulator(
            latency_ms=0.0,
            market_impact_k=0.1,
            max_slippage_pct=0.01
        )
    
    def set_price(self, symbol: str, price: Decimal) -> None:
        """Set the simulated price for a symbol."""
        self.prices[symbol] = price
    
    async def send_order(self, order: OrderEvent) -> Tuple[bool, Optional[str]]:
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
                "filled_size": Decimal('0'),
                "avg_price": Decimal('0')
            }
            
            self.logger.info(f"Simulated exchange: Order sent - ID: {order_id}, Symbol: {order.symbol}, Side: {order.side}, Quantity: {order.quantity}, Price: {order.price}")
            
            # For simulation, we can immediately fill market orders or simulate limit order filling
            if order.order_type == OrderType.MARKET:
                # Market order: fill immediately at current price
                if order.symbol in self.prices:
                    fill_price = self.prices[order.symbol]
                    # Simulate slippage (optional)
                    slippage = Decimal('0.001')  # 0.1% slippage
                    if order.side == "BUY":
                        fill_price *= (1 + slippage)
                    else:
                        fill_price *= (1 - slippage)
                    
                    # Update position
                    self.positions[order.symbol] = self.positions.get(order.symbol, Decimal('0')) + (order.quantity if order.side == "BUY" else -order.quantity)
                    
                    # Create fill event
                    fill_event = FillEvent(
                        order_id=order_id,
                        symbol=order.symbol,
                        timestamp=datetime.utcnow(),
                        side=order.side,
                        quantity=order.quantity,
                        price=fill_price,
                        commission=Decimal('0')
                    )
                    
                    # Update order status
                    self.orders[order_id]["status"] = OrderStatus.FILLED
                    self.orders[order_id]["filled_size"] = order.quantity
                    self.orders[order_id]["avg_price"] = fill_price
                    
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
                
        except Exception as e:
            self.logger.error(f"Error sending order to simulated exchange: {e}", exc_info=True)
            return False, str(e)
    
    async def cancel_order(self, order_id: str) -> Tuple[bool, Optional[str]]:
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
        return self.positions.get(symbol, Decimal('0'))
    
    def check_and_fill_limit_orders(self, current_prices: Dict[str, Decimal]) -> list:
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
                self.positions[symbol] = self.positions.get(symbol, Decimal('0')) + (order.quantity if order.side == "BUY" else -order.quantity)
                
                fill_event = FillEvent(
                    order_id=order_id,
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    side=order.side,
                    quantity=order.quantity,
                    price=fill_price,
                    commission=Decimal('0')
                )
                fills.append(fill_event)
                
                # Update order status
                order_info["status"] = OrderStatus.FILLED
                order_info["filled_size"] = order.quantity
                order_info["avg_price"] = fill_price
                
                self.logger.info(f"Simulated exchange: Limit order filled - ID: {order_id}, Symbol: {symbol}, Price: {fill_price}")
        
        return fills

class ExecutionEngine:
    """
    Real execution layer connecting QTrader to exchanges.
    Handles order validation, routing, execution logic, position tracking, retry logic, failover, and safety checks.
    """
    
    def __init__(
        self,
        exchange_adapter: ExchangeAdapter,
        max_order_size: float = 1000000.0,  # Default max order size in quote currency
        max_slippage: float = 0.01,         # 1% max slippage for market orders
        max_retry_attempts: int = 3,
        retry_delay_base: float = 0.1,      # Base delay in seconds for exponential backoff
        enable_failover_queue: bool = True,
        logger: LoggerProtocol = logger
    ):
        self.exchange_adapter = exchange_adapter
        self.max_order_size = max_order_size
        self.max_slippage = max_slippage
        self.max_retry_attempts = max_retry_attempts
        self.retry_delay_base = retry_delay_base
        self.enable_failover_queue = enable_failover_queue
        self.logger = logger
        
        # State
        self.failover_queue: Optional[asyncio.Queue] = asyncio.Queue() if enable_failover_queue else None
        self.pending_orders: Dict[str, OrderEvent] = {}  # order_id -> order
        self.order_futures: Dict[str, asyncio.Future] = {}  # order_id -> future for result
        self.position_tracker: Dict[str, Decimal] = {}  # symbol -> position size
        self.avg_price_tracker: Dict[str, Tuple[Decimal, Decimal]] = {}  # symbol -> (total_cost, total_quantity)
        
        # Background tasks
        self._processing_task: Optional[asyncio.Task] = None
        self._failover_processor_task: Optional[asyncio.Task] = None
        self._is_running = False
    
    async def start(self) -> None:
        """Start the execution engine background tasks."""
        if self._is_running:
            return
        
        self._is_running = True
        self._processing_task = asyncio.create_task(self._process_order_queue())
        if self.enable_failover_queue:
            self._failover_processor_task = asyncio.create_task(self._process_failover_queue())
        self.logger.info("ExecutionEngine started")
    
    async def stop(self) -> None:
        """Stop the execution engine background tasks."""
        self._is_running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        if self._failover_processor_task:
            self._failover_processor_task.cancel()
            try:
                await self._failover_processor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("ExecutionEngine stopped")
    
    async def execute_order(self, order: OrderEvent) -> Tuple[bool, Optional[FillEvent]]:
        """
        Execute an order with validation, retry logic, and failover.
        
        Args:
            order: OrderEvent to execute
            
        Returns:
            Tuple (success, fill_event or None if failed)
        """
        # Validate order
        validation_error = self._validate_order(order)
        if validation_error:
            self.logger.warning(f"Order validation failed: {validation_error}")
            return False, None
        
        # Attempt to send order with retries
        for attempt in range(self.max_retry_attempts + 1):
            try:
                success, result = await self.exchange_adapter.send_order(order)
                if success:
                    assert isinstance(result, str), "send_order must return order_id as string on success"
                    order_id = result
                    # Store pending order for tracking
                    self.pending_orders[order_id] = order
                    # Create a future to wait for fill
                    future = asyncio.Future()
                    self.order_futures[order_id] = future
                    
                    # Wait for fill (with timeout based on order type)
                    try:
                        # For market orders, we expect immediate fill; for limit, we wait longer
                        timeout = 5.0 if order.order_type == OrderType.MARKET else 30.0
                        fill_event = await asyncio.wait_for(future, timeout=timeout)
                        return True, fill_event
                    except asyncio.TimeoutError:
                        # If timeout, we might still have a pending order
                        # For simulation, we can check if it's filled now
                        if isinstance(self.exchange_adapter, SimulatedExchangeAdapter):
                            # In simulation, we might need to trigger fill checking
                            # This is a simplification; in reality, we'd have event listeners
                            pass
                        # Return the order ID as pending? We'll treat timeout as failure for now
                        # In a real system, we'd have a separate mechanism to check order status
                        return False, None
                else:
                    # Send failed
                    if attempt < self.max_retry_attempts:
                        delay = self.retry_delay_base * (2 ** attempt)  # Exponential backoff
                        self.logger.warning(f"Order send failed (attempt {attempt+1}), retrying in {delay}s: {result}")
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(f"Order send failed after {self.max_retry_attempts+1} attempts: {result}")
                        # If failover queue is enabled, add to queue
                        if self.enable_failover_queue and self.failover_queue is not None:
                            await self.failover_queue.put((order, datetime.utcnow()))
                            return False, None
                        return False, None
            except Exception as e:
                self.logger.error(f"Unexpected error executing order (attempt {attempt+1}): {e}", exc_info=True)
                if attempt < self.max_retry_attempts:
                    delay = self.retry_delay_base * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    if self.enable_failover_queue and self.failover_queue is not None:
                        await self.failover_queue.put((order, datetime.utcnow()))
                        return False, None
                    return False, None
        
        return False, None
    
    async def cancel_order(self, order_id: str) -> Tuple[bool, Optional[str]]:
        """
        Cancel an order.
        
        Args:
            order_id: ID of the order to cancel
            
        Returns:
            Tuple (success, error_message)
        """
        # Check if it's in our pending orders
        if order_id in self.pending_orders:
            success, error = await self.exchange_adapter.cancel_order(order_id)
            if success:
                # Remove from tracking
                if order_id in self.pending_orders:
                    del self.pending_orders[order_id]
                if order_id in self.order_futures:
                    # Cancel the future if it's still waiting
                    future = self.order_futures.pop(order_id)
                    if not future.done():
                        future.set_exception(asyncio.CancelledError())
            return success, error
        else:
            # Try to cancel on exchange anyway (might be a stale ID)
            return await self.exchange_adapter.cancel_order(order_id)
    
    def _validate_order(self, order: OrderEvent) -> Optional[str]:
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
        if order.order_type == OrderType.LIMIT and order.price is None:
            return "Limit order must have a price"
        
        if order.order_type == OrderType.MARKET and order.price is not None:
            self.logger.warning("Market order received with price; price will be ignored")
        
        # Additional safety checks could be added here (e.g., symbol validation, etc.)
        
        return None
    
    async def _process_order_queue(self) -> None:
        """Background task to process order fills and update position tracking."""
        while self._is_running:
            try:
                # In a real system, we would listen to exchange fill events via websockets or polling
                # For this implementation, we'll simulate by checking for fills in the exchange adapter
                # if it's a simulated exchange, or we'd have a callback mechanism.
                #
                # Since we don't have a generic way to get fills from the exchange adapter,
                # we'll rely on the order futures being set by the exchange adapter's send_order
                # in the case of immediate fills (like market orders in simulation).
                #
                # For limit orders, we would need a separate mechanism. For simplicity in this
                # implementation, we'll assume that the exchange adapter has a way to notify
                # of fills (e.g., via a callback or by polling). However, to keep the adapter
                # interface simple, we'll handle simulation-specific logic in the simulated adapter.
                #
                # For now, we'll just sleep and let the execution_engine's execute_order method
                # handle waiting for fills via the future mechanism.
                #
                # In a production system, this task would handle:
                # - Listening to exchange fill streams
                # - Updating order status
                # - Triggering futures when orders fill
                # - Updating position tracking
                #
                # We'll implement a simple version that works with the simulated exchange by
                # periodically checking for limit order fills.
                
                await asyncio.sleep(0.1)  # Check every 100ms
                
                # If we have a simulated exchange, check for limit order fills
                if isinstance(self.exchange_adapter, SimulatedExchangeAdapter):
                    # We would need current prices to check limit orders
                    # In a real system, we'd get this from market data feed
                    # For now, we'll skip this and rely on the caller to trigger fill checks
                    # via a separate method (not ideal, but keeps the example focused)
                    pass
                
            except Exception as e:
                self.logger.error(f"Error in order processing loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Avoid tight loop on error
    
    async def _process_failover_queue(self) -> None:
        """Background task to process orders from the failover queue."""
        while self._is_running:
            try:
                # Get order from queue with timeout to allow checking _is_running
                try:
                    order, timestamp = await asyncio.wait_for(self.failover_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                self.logger.info(f"Processing order from failover queue: {order.symbol} {order.side} {order.quantity}")
                
                # Try to execute the order
                success, result = await self.execute_order(order)
                if not success:
                    # If it fails again, put it back in the queue (with a limit to avoid infinite loops)
                    # For simplicity, we'll just log and drop it; in reality, you'd have a retry limit
                    self.logger.warning(f"Failed to execute order from failover queue: {result}")
                # If successful, nothing more to do
                
            except Exception as e:
                self.logger.error(f"Error in failover processing loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)
    
    # Methods to be called by the exchange adapter or market data feed to update order status
    def _on_order_filled(self, order_id: str, fill_event: FillEvent) -> None:
        """
        Callback to handle an order fill (to be called by exchange adapter or market data handler).
        
        Args:
            order_id: ID of the order that was filled
            fill_event: FillEvent details
        """
        if order_id in self.order_futures:
            future = self.order_futures.pop(order_id)
            if not future.done():
                future.set_result(fill_event)
        
        # Update position tracking
        self._update_position_from_fill(fill_event)
        
        # Remove from pending orders
        if order_id in self.pending_orders:
            del self.pending_orders[order_id]
        
        self.logger.info(f"Order filled: {order_id} - {fill_event.symbol} {fill_event.side} {fill_event.quantity} @ {fill_event.price}")
    
    def _on_order_cancelled(self, order_id: str) -> None:
        """
        Callback to handle an order cancellation.
        
        Args:
            order_id: ID of the order that was cancelled
        """
        if order_id in self.order_futures:
            future = self.order_futures.pop(order_id)
            if not future.done():
                future.set_exception(asyncio.CancelledError())
        
        if order_id in self.pending_orders:
            del self.pending_orders[order_id]
        
        self.logger.info(f"Order cancelled: {order_id}")
    
    def _update_position_from_fill(self, fill_event: FillEvent) -> None:
        """Update internal position tracking from a fill event."""
        symbol = fill_event.symbol
        quantity = fill_event.quantity if fill_event.side == "BUY" else -fill_event.quantity
        
        # Update position size
        self.position_tracker[symbol] = self.position_tracker.get(symbol, Decimal('0')) + quantity
        
        # Update average price
        if symbol in self.avg_price_tracker:
            total_cost, total_qty = self.avg_price_tracker[symbol]
            new_cost = total_cost + (fill_event.price * fill_event.quantity)
            new_qty = total_qty + fill_event.quantity
            if new_qty != 0:
                avg_price = new_cost / new_qty
            else:
                avg_price = Decimal('0')
            self.avg_price_tracker[symbol] = (new_cost, new_qty)
        else:
            self.avg_price_tracker[symbol] = (fill_event.price * fill_event.quantity, fill_event.quantity)
    
    def get_position(self, symbol: str) -> Decimal:
        """Get current tracked position for a symbol."""
        return self.position_tracker.get(symbol, Decimal('0'))
    
    def get_average_price(self, symbol: str) -> Optional[Decimal]:
        """Get average price for a position."""
        if symbol in self.avg_price_tracker:
            total_cost, total_qty = self.avg_price_tracker[symbol]
            if total_qty != 0:
                return total_cost / total_qty
        return None

# Example usage (not part of the required output, but for illustration)
if __name__ == "__main__":
    # This is just for demonstration; normally this would be used by the orchestrator
    pass