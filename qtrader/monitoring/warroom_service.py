import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger

from .metrics import MetricsAggregator


class WarRoomService:
    """
    Central service for real-time monitoring of trading activity.
    Coordinates metrics aggregation and dashboard data serving.
    """

    def __init__(self, update_interval_s: float = 1.0) -> None:
        """
        Args:
            update_interval_s: Interval for broadcasting dashboard updates.
        """
        self.aggregator = MetricsAggregator()
        self.update_interval_s = update_interval_s
        self._running = False
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._latest_snapshot: dict[str, Any] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

    def add_subscriber(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for periodic snapshot broadcasts."""
        self._subscribers.append(callback)

    async def start(self) -> None:
        """Start the background event processing task."""
        self._running = True
        process_task = asyncio.create_task(self._process_events())
        self._tasks.add(process_task)
        process_task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        """Stop all background tasks."""
        self._running = False

    def push_event(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Push a new event into the processing queue.
        Thread-safe entry point for external emitters.
        """
        self._event_queue.put_nowait({"type": event_type, "data": data})

    async def _process_events(self) -> None:
        """Background task to process events from the queue."""
        while self._running:
            try:
                event = await self._event_queue.get()
                event_type = event["type"]
                data = event["data"]

                if event_type == "pnl_update":
                    self.aggregator.update_pnl(nav=data["nav"], realized=data.get("realized", 0.0))
                elif event_type == "latency_record":
                    self.aggregator.record_latency(
                        stage=data["stage"], latency_ms=data["latency_ms"]
                    )
                
                # Zero Latency: Update snapshot and broadcast immediately after processing
                self._latest_snapshot = self.aggregator.get_summary()
                for subscriber in self._subscribers:
                    try:
                        subscriber(self._latest_snapshot)
                    except Exception as e:
                        logger.info(f"Subscriber error: {e}")

            except (KeyError, TypeError, ValueError) as e:
                logger.info(f"Error processing event {event_type}: {e}")
            finally:
                self._event_queue.task_done()

    # Redundant broadcast loop removed for event-driven architecture

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        """
        Get the current state of metrics for REST API consumption.
        """
        if not self._latest_snapshot:
            return self.aggregator.get_summary()
        return self._latest_snapshot

    def get_health(self) -> dict[str, Any]:
        """
        Return service health status.
        """
        return {
            "status": "healthy" if self._running else "stopped",
            "queue_size": self._event_queue.qsize(),
            "timestamp": datetime.now().isoformat(),
        }
