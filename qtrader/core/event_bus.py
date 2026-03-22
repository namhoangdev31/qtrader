import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Union
import time

from .types import EventType, EventBusProtocol, LoggerProtocol


class EventBus:
    """Production-grade async event bus with backpressure handling, retries, timeouts, and dead letter queue."""

    def __init__(
        self,
        logger: Optional[LoggerProtocol] = None,
        *,
        maxsize: int = 0,
        max_retries: int = 3,
        base_retry_delay: float = 0.1,
        handler_timeout: float = 5.0,
        dead_letter_queue_maxsize: int = 1000,
    ):
        """
        Initialize the async event bus.

        Args:
            logger: Optional logger instance
            maxsize: Maximum size of the event queue (0 for unlimited)
            max_retries: Maximum number of retry attempts for failed handlers
            base_retry_delay: Base delay in seconds for exponential backoff
            handler_timeout: Timeout in seconds for each handler execution
            dead_letter_queue_maxsize: Maximum size of the dead letter queue
        """
        self._subscribers: Dict[EventType, List[Callable]] = {et: [] for et in EventType}
        self._logger = logger or logging.getLogger(__name__)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._dead_letter_queue: asyncio.Queue = asyncio.Queue(maxsize=dead_letter_queue_maxsize)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay
        self._handler_timeout = handler_timeout

        # Metrics for monitoring
        self._events_processed = 0
        self._events_failed = 0
        self._events_retried = 0
        self._dead_letter_count = 0

    async def start(self) -> None:
        """Start the event bus processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_events())
        self._logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop the event bus processing loop."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._logger.info("Event bus stopped")

    async def _process_events(self) -> None:
        """Process events from the main queue with retry and timeout handling."""
        while self._running:
            try:
                # Get event from queue (waits if empty)
                event_type, data = await self._queue.get()
                if event_type in self._subscribers:
                    # Process each subscriber concurrently but with error handling
                    tasks = []
                    for callback in self._subscribers[event_type]:
                        task = asyncio.create_task(
                            self._safe_handler(callback, event_type, data)
                        )
                        tasks.append(task)
                    
                    # Wait for all handlers to complete
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                
                self._queue.task_done()
                self._events_processed += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in event bus loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)  # Prevent tight loop on persistent errors

    async def _safe_handler(
        self, callback: Callable, event_type: EventType, data: Any
    ) -> None:
        """Execute a handler with retries, timeout, and exponential backoff."""
        last_exception: Optional[BaseException] = None
        for attempt in range(self._max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await asyncio.wait_for(
                        callback(data), timeout=self._handler_timeout
                    )
                else:
                    # For synchronous callbacks, run in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, lambda: callback(data)
                    )
                # Success - break out of retry loop
                return
            except asyncio.TimeoutError as e:
                last_exception = e
                self._logger.warning(
                    f"Handler timeout for event {event_type} (attempt {attempt + 1}/{self._max_retries + 1})"
                )
            except Exception as e:
                last_exception = e
                self._logger.warning(
                    f"Handler failed for event {event_type}: {e} (attempt {attempt + 1}/{self._max_retries + 1})"
                )
            
            # If we have retries left, wait with exponential backoff
            if attempt < self._max_retries:
                delay = self._base_retry_delay * (2 ** attempt)
                self._logger.debug(
                    f"Retrying handler for {event_type} in {delay:.2f}s"
                )
                await asyncio.sleep(delay)
                self._events_retried += 1
        
        # All retries exhausted - send to dead letter queue
        if last_exception is not None:
            self._logger.error(
                f"Handler failed for event {event_type} after {self._max_retries + 1} attempts. "
                f"Last error: {last_exception}"
            )
            self._events_failed += 1
            await self._enqueue_dead_letter(event_type, data, last_exception)
        else:
            # This shouldn't happen, but just in case
            self._logger.error(
                f"Handler failed for event {event_type} after {self._max_retries + 1} attempts. "
                f"No exception recorded"
            )
            self._events_failed += 1
            await self._enqueue_dead_letter(
                event_type, 
                data, 
                Exception("Unknown error after all retries")
            )

    async def _enqueue_dead_letter(
        self, event_type: EventType, data: Any, exception: BaseException
    ) -> None:
        """Enqueue failed event to dead letter queue."""
        try:
            dead_letter_data = {
                "event_type": event_type,
                "data": data,
                "exception": str(exception),
                "timestamp": time.time(),
                "retry_count": self._max_retries + 1,
            }
            await self._dead_letter_queue.put(dead_letter_data)
            self._dead_letter_count += 1
            self._logger.warning(
                f"Event {event_type} sent to dead letter queue after {self._max_retries + 1} failed attempts. "
                f"DLQ size: {self._dead_letter_queue.qsize()}"
            )
        except asyncio.QueueFull:
            self._logger.error(
                f"Dead letter queue full. Dropping event for {event_type}"
            )

    async def publish(self, event_type: EventType, data: Any) -> None:
        """
        Publish an event to the bus with backpressure handling.

        Waits if the queue is full (based on maxsize).
        """
        await self._queue.put((event_type, data))

    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        """Subscribe a callback to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable) -> None:
        """Unsubscribe a callback from an event type."""
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    # Monitoring and inspection methods
    def get_metrics(self) -> Dict[str, Union[int, float]]:
        """Get current event bus metrics."""
        return {
            "events_processed": self._events_processed,
            "events_failed": self._events_failed,
            "events_retried": self._events_retried,
            "dead_letter_count": self._dead_letter_count,
            "queue_size": self._queue.qsize(),
            "dead_letter_queue_size": self._dead_letter_queue.qsize(),
        }

    async def get_dead_letters(self, max_count: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve dead letter events for inspection (non-destructive peek).

        Note: This does not remove items from the dead letter queue.
        """
        dead_letters = []
        temp_queue = asyncio.Queue()
        
        # Extract items without removing them
        try:
            while len(dead_letters) < max_count and not self._dead_letter_queue.empty():
                item = await self._dead_letter_queue.get()
                dead_letters.append(item)
                await temp_queue.put(item)
            
            # Put items back
            while not temp_queue.empty():
                item = await temp_queue.get()
                await self._dead_letter_queue.put(item)
        except Exception as e:
            self._logger.error(f"Error retrieving dead letters: {e}")
        
        return dead_letters