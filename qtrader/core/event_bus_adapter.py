# File: qtrader/core/event_bus_adapter.py
from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar, Generic

from qtrader.core.event import EventType
from qtrader.core.event_bus import EventBus

T = TypeVar("T")

class EventBusAdapter(Generic[T]):
    """
    High-performance adapter for the EventBus to eliminate polling patterns.
    Provides utility methods for waiting on specific event conditions without asyncio.sleep.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._loop = asyncio.get_event_loop()

    async def publish(self, event_type: EventType, data: Any) -> None:
        """
        Publishes an event to the bus.
        """
        await self._bus.publish(event_type, data)

    def subscribe(self, event_type: EventType, callback: Callable[[Any], Any]) -> None:
        """
        Subscribes a handler to an event type.
        """
        self._bus.subscribe(event_type, callback)

    def unsubscribe(self, event_type: EventType, callback: Callable[[Any], Any]) -> None:
        """
        Unsubscribes a handler from an event type.
        """
        self._bus.unsubscribe(event_type, callback)

    async def wait_for_event(
        self, 
        event_type: EventType, 
        predicate: Callable[[Any], bool] | None = None,
        timeout: float | None = None
    ) -> Any:
        """
        Wait for a specific event to occur without using asyncio.sleep.
        Uses a Future that is resolved when the matching event is received.
        
        Args:
            event_type: The EventType to wait for.
            predicate: Optional function to filter events.
            timeout: Maximum time to wait in seconds.
            
        Returns:
            The data associated with the event.
            
        Raises:
            asyncio.TimeoutError: If the event is not received within the timeout.
        """
        future: asyncio.Future[Any] = self._loop.create_future()

        def handler(data: Any) -> None:
            if future.done():
                return
            
            if predicate is None or predicate(data):
                future.set_result(data)

        self.subscribe(event_type, handler)
        
        try:
            if timeout is not None:
                return await asyncio.wait_for(future, timeout=timeout)
            return await future
        finally:
            self.unsubscribe(event_type, handler)
