import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger

from qtrader.core.bus import EventBus
from qtrader.core.events import EventType, FillEvent, OrderEvent, RiskEvent, SystemEvent

from .metrics import MetricsAggregator


class WarRoomService:
    """
    Reactive monitoring service for real-time trading oversight.
    Subscribes to EventBus to aggregate metrics without polling.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        """
        Args:
            event_bus: Optional global production event bus.
        """
        self.aggregator = MetricsAggregator()
        self.bus = event_bus
        self._running = False
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._latest_snapshot: dict[str, Any] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

        if self.bus:
            self._subscribe_to_bus()
        else:
            logger.warning(
                "WarRoomService initialized without EventBus. Call set_bus() later to enable reactive monitoring."
            )

    def set_bus(self, event_bus: EventBus) -> None:
        """Link the service to a production EventBus and enable subscriptions."""
        self.bus = event_bus
        self._subscribe_to_bus()
        logger.info("WarRoomService linked to EventBus")

    def _subscribe_to_bus(self) -> None:
        """Internal helper to register event handlers."""
        if not self.bus:
            return
        self.bus.subscribe(EventType.FILL, self._handle_fill)
        self.bus.subscribe(EventType.ORDER, self._handle_order)
        self.bus.subscribe(EventType.RISK, self._handle_risk)
        self.bus.subscribe(EventType.DRIFT, self._handle_drift)
        self.bus.subscribe(EventType.ERROR, self._handle_error)

    def add_subscriber(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for real-time snapshot broadcasts."""
        self._subscribers.append(callback)

    async def start(self) -> None:
        """Start the background metrics processing task."""
        if self._running:
            return
        self._running = True
        process_task = asyncio.create_task(self._process_events())
        self._tasks.add(process_task)
        process_task.add_done_callback(self._tasks.discard)
        logger.info("WarRoomService metrics engine started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # EventBus Handlers - Just push to internal FIFO queue for high-performance decoupling
    async def _handle_fill(self, event: FillEvent) -> None:
        self._event_queue.put_nowait({"type": "fill", "data": event})

    async def _handle_order(self, event: OrderEvent) -> None:
        self._event_queue.put_nowait({"type": "order", "data": event})

    async def _handle_risk(self, event: RiskEvent) -> None:
        self._event_queue.put_nowait({"type": "risk", "data": event})

    async def _handle_drift(self, event: SystemEvent) -> None:
        self._event_queue.put_nowait({"type": "drift", "data": event})

    async def _handle_error(self, event: Any) -> None:
        self._event_queue.put_nowait({"type": "error", "data": event})

    async def _process_events(self) -> None:
        """Background task to translate low-level events into aggregated metrics."""
        while self._running:
            try:
                event = await self._event_queue.get()
                etype = event["type"]
                data = event["data"]

                if etype == "fill":
                    self.aggregator.on_fill(
                        symbol=data.symbol,
                        quantity=float(data.quantity),
                        price=float(data.price),
                        side=data.side,
                    )
                elif etype == "order":
                    self.aggregator.on_order(
                        symbol=data.symbol, quantity=float(data.quantity), side=data.side
                    )
                elif etype == "risk":
                    self.aggregator.on_risk_alert()
                elif etype == "pnl_update":
                    self.aggregator.update_pnl(nav=data["nav"], realized=data.get("realized", 0.0))

                # Push real-time snapshot to subscribers
                self._latest_snapshot = self.aggregator.get_summary()
                for subscriber in self._subscribers:
                    try:
                        subscriber(self._latest_snapshot)
                    except Exception as e:
                        logger.error(f"WarRoom broadcast failure: {e}")

            except Exception as e:
                logger.error(f"WarRoom event processing error: {e}")
            finally:
                self._event_queue.task_done()

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        return self._latest_snapshot or self.aggregator.get_summary()

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._running else "stopped",
            "metrics_buffered": self._event_queue.qsize(),
            "timestamp": datetime.now().isoformat(),
        }
