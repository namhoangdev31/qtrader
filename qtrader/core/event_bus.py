import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from .types import EventType, EventBusProtocol, LoggerProtocol


class EventBus:
    """Async event bus for publish/subscribe pattern."""

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        self._subscribers: Dict[EventType, List[Callable]] = {et: [] for et in EventType}
        self._logger = logger or logging.getLogger(__name__)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

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
        """Process events from the queue."""
        while self._running:
            try:
                event_type, data = await self._queue.get()
                if event_type in self._subscribers:
                    for callback in self._subscribers[event_type]:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(data)
                            else:
                                callback(data)
                        except Exception as e:
                            self._logger.error(
                                f"Error in event callback for {event_type}: {e}",
                                exc_info=True
                            )
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in event bus loop: {e}", exc_info=True)

    async def publish(self, event_type: EventType, data: Any) -> None:
        """Publish an event to the bus."""
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