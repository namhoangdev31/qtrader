import asyncio
import logging
from typing import Any

from qtrader.core.event import EventType, RetryOrderEvent
from qtrader.core.types import EventBusProtocol


class RetryHandler:
    """Handles event-driven retries for failed order submissions."""
    
    def __init__(self, event_bus: EventBusProtocol, execution_engine: Any, max_retries: int = 3) -> None:
        self.event_bus = event_bus
        self.execution_engine = execution_engine
        self.max_retries = max_retries
        self._log = logging.getLogger("qtrader.execution.retry_handler")

    async def start(self) -> None:
        """Subscribe to retry events."""
        self.event_bus.subscribe(EventType.RETRY_ORDER, self._on_retry_event)
        self._log.info("RetryHandler started and subscribed to RETRY_ORDER events.")

    async def _on_retry_event(self, event: RetryOrderEvent) -> None:
        """Process a retry request."""
        order = event.order
        attempt = event.attempt
        
        if attempt > self.max_retries:
            self._log.error(f"Max retries ({self.max_retries}) exceeded for order {order.order_id}.")
            return
            
        self._log.info(f"Retrying order {order.order_id} (Attempt {attempt})")
        
        # Exponential backoff based on attempt
        delay = min(0.1 * (2 ** (attempt - 1)), 5.0)
        await asyncio.sleep(delay)
        
        try:
            # We call the non-blocking execute_order
            await self.execution_engine.execute_order(order, attempt=attempt)
        except Exception as e:
            self._log.error(f"Error during order retry: {e}", exc_info=True)
