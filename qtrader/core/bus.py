import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from qtrader.core.event import Event, EventType
from qtrader.core.logger import log

T = TypeVar("T", bound=Event)
Handler = Callable[[T], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self, queue_maxsize: int = 10000, handler_timeout_s: float | None = None) -> None:
        self._handlers: dict[EventType, list[Handler[Any]]] = {}
        self._queue: asyncio.Queue[object] = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False
        self._log = log.bind(module="eventbus")
        self._STOP = object()
        self._handler_timeout_s = handler_timeout_s

        # Minimal, dependency-free metrics.
        self.published_total = 0
        self.processed_total = 0
        self.handler_errors_total = 0
        self.handler_timeouts_total = 0
        self.max_queue_depth_seen = 0
        self.last_event_process_ms: float | None = None

    def subscribe(self, event_type: EventType, handler: Handler[Any]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        self.published_total += 1
        # Use a bounded queue to create backpressure when upstream is too fast.
        await self._queue.put(event)
        qsize = self._queue.qsize()
        self.max_queue_depth_seen = max(self.max_queue_depth_seen, qsize)

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def get_stats(self) -> dict[str, object]:
        return {
            "published_total": self.published_total,
            "processed_total": self.processed_total,
            "handler_errors_total": self.handler_errors_total,
            "handler_timeouts_total": self.handler_timeouts_total,
            "max_queue_depth_seen": self.max_queue_depth_seen,
            "queue_size": self._queue.qsize(),
            "last_event_process_ms": self.last_event_process_ms,
        }

    async def shutdown(self) -> None:
        """Stop the bus and wake the consumer loop even if it's blocked on queue.get()."""
        self._running = False
        await self._queue.put(self._STOP)

    async def _process_event(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if self._handler_timeout_s is None:
            tasks = [handler(event) for handler in handlers]
        else:
            tasks = [
                asyncio.wait_for(handler(event), timeout=self._handler_timeout_s)
                for handler in handlers
            ]
        if not tasks:
            return

        # Avoid one buggy handler taking down the whole bus.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                if isinstance(res, asyncio.TimeoutError):
                    self.handler_timeouts_total += 1
                else:
                    self.handler_errors_total += 1
                self._log.bind(
                    event_type=event.type.name,
                    trace_id=event.trace_id
                ).error("Event handler failed", exc_info=res)

    async def start(self) -> None:
        self._running = True
        while True:
            item = await self._queue.get()
            try:
                if item is self._STOP:
                    break
                start = time.perf_counter()
                await self._process_event(item)  # type: ignore[arg-type]
                
                # Global Latency Enforcement: Audit every event processing cycle
                from qtrader.core.latency import LatencyEnforcer, LATENCY_MAX_MS
                report = LatencyEnforcer.check_breach(
                    tag=f"event_{getattr(item, 'type', 'unknown')}", 
                    start_time=start, 
                    threshold=LATENCY_MAX_MS
                )
                
                self.processed_total += 1
                self.last_event_process_ms = report.duration_ms
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        self._running = False
