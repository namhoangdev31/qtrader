from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from qtrader.core.backpressure_controller import BackpressureController
from qtrader.core.events import EVENT_TYPE_MAP, BaseEvent, EventType
from qtrader.core.partition_manager import PartitionManager

try:
    import redis.asyncio as redis
except ImportError:
    redis = None
if TYPE_CHECKING:
    from collections.abc import Callable

    from qtrader.core.event_store import BaseEventStore
logger = logging.getLogger(__name__)


class EventBus:
    def __init__(
        self,
        num_partitions: int = 16,
        event_store: BaseEventStore | None = None,
        *,
        handler_timeout: float = 5.0,
        max_retries: int = 3,
        redis_url: str | None = None,
    ) -> None:
        self._subscribers: dict[EventType, list[Callable]] = {et: [] for et in EventType}
        self._partition_manager = PartitionManager(num_partitions=num_partitions)
        self._backpressure = BackpressureController()
        self._event_store = event_store
        self._queues: dict[int, asyncio.Queue[BaseEvent]] = {
            i: asyncio.Queue(maxsize=20000) for i in range(num_partitions)
        }
        self._running = False
        self._worker_tasks: list[asyncio.Task] = []
        self._handler_timeout = handler_timeout
        self._max_retries = max_retries
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._redis_listener_task: asyncio.Task | None = None
        self._redis_channel = "qtrader:events"
        self._events_processed_count = 0
        self._events_dropped_count = 0
        self._last_latencies: dict[int, float] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._partition_manager.num_partitions):
            task = asyncio.create_task(self._partition_worker(i))
            self._worker_tasks.append(task)
        if redis and self._redis_url:
            try:
                self._redis = redis.from_url(self._redis_url, decode_responses=True)
                self._redis_listener_task = asyncio.create_task(self._redis_listener())
                logger.info(f"[EVENT_BUS] Redis bridge active on {self._redis_channel}")
            except Exception as e:
                logger.error(f"[EVENT_BUS] Failed to start Redis bridge: {e}")
        logger.info(f"EventBus started with {len(self._worker_tasks)} partitions")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks = []
        if self._redis_listener_task:
            self._redis_listener_task.cancel()
            self._redis_listener_task = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("EventBus stopped")

    async def publish(self, event: BaseEvent) -> bool:
        if not self._running:
            logger.warning(
                f"[EVENT_BUS] Attempted to publish to stopped EventBus: {event.event_type}"
            )
            return False
        p_index = self._partition_manager.get_partition_index(event)
        q_size = self._queues[p_index].qsize()
        if self._backpressure.should_drop(q_size, event.event_type):
            self._events_dropped_count += 1
            logger.warning(
                f"[EVENT_BUS] Dropped event {event.event_type} due to backpressure (queue_size={q_size})"
            )
            return False
        if not event.partition_key:
            event = event.model_copy(
                update={"partition_key": self._partition_manager.get_partition_key(event)}
            )
        try:
            await self._queues[p_index].put(event)
            if self._redis and (not event.is_remote):
                asyncio.create_task(
                    self._redis.publish(self._redis_channel, event.model_dump_json())
                )
            logger.debug(f"[EVENT_BUS] Published {event.event_type} to partition {p_index}")
            return True
        except asyncio.QueueFull:
            self._events_dropped_count += 1
            logger.error(
                f"[EVENT_BUS] Queue full for partition {p_index}, dropping event {event.event_type}"
            )
            return False

    async def _partition_worker(self, index: int) -> None:
        queue = self._queues[index]
        while self._running:
            try:
                event = await queue.get()
                start_time = time.perf_counter()
                if event.event_type in self._subscribers:
                    handlers = self._subscribers[event.event_type]
                    for handler in handlers:
                        await self._safe_deliver(handler, event)
                if self._event_store:
                    await self._event_store.append(event)
                duration = (time.perf_counter() - start_time) * 1000
                self._last_latencies[index] = duration
                self._events_processed_count += 1
                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Partition worker {index} encountered error: {e}")

    async def _redis_listener(self) -> None:
        if not self._redis:
            return
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._redis_channel)
        while self._running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data_json = message["data"]
                    try:
                        raw_data = json.loads(data_json)
                        et_str = raw_data.get("event_type")
                        et = EventType(et_str) if et_str else None
                        event_cls = EVENT_TYPE_MAP.get(et, BaseEvent)
                        event = event_cls.model_validate_json(data_json)
                    except Exception as e:
                        logger.error(
                            f"[EVENT_BUS] Deserialization failed for type {(et_str if 'et_str' in locals() else 'unknown')}: {e}"
                        )
                        continue
                    event = event.model_copy(update={"is_remote": True})
                    await self.publish(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EVENT_BUS] Redis bridge listener error: {e}")
                continue

    async def _safe_deliver(self, handler: Callable, event: BaseEvent) -> None:
        current_event = event
        for attempt in range(1, self._max_retries + 2):
            try:
                if attempt > 1:
                    current_event = current_event.model_copy(update={"delivery_attempt": attempt})
                await asyncio.wait_for(handler(current_event), timeout=self._handler_timeout)
                return
            except Exception as e:
                if attempt > self._max_retries:
                    logger.error(
                        f"Handler failed after total {attempt} attempts for {current_event.event_id}: {e}"
                    )
                else:
                    continue

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def get_metrics(self) -> dict[str, Any]:
        return {
            "total_processed": self._events_processed_count,
            "total_dropped": self._events_dropped_count,
            "avg_latency_ms": sum(self._last_latencies.values()) / len(self._last_latencies)
            if self._last_latencies
            else 0.0,
            "queue_depths": {i: q.qsize() for (i, q) in self._queues.items()},
            "throughput": self._events_processed_count,
        }
