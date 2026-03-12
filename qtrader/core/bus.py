import asyncio
from typing import Callable, Coroutine, Dict, List, Type, TypeVar

from qtrader.core.event import Event, EventType

T = TypeVar("T", bound=Event)
Handler = Callable[[T], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[EventType, List[Handler[Any]]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: EventType, handler: Handler[Any]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        await self._queue.put(event)

    async def _process_event(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        tasks = [handler(event) for handler in handlers]
        if tasks:
            await asyncio.gather(*tasks)

    async def start(self) -> None:
        self._running = True
        while self._running:
            event = await self._queue.get()
            try:
                await self._process_event(event)
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        self._running = False
