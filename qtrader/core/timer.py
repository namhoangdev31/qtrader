import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from qtrader.core.events import EventType, SystemEvent, SystemPayload
from qtrader.core.types import EventBusProtocol


def HeartbeatEvent(timestamp: datetime | None = None) -> SystemEvent:
    """Periodic system heartbeat event."""
    return SystemEvent(
        source="TimerService",
        trace_id=uuid4(),
        payload=SystemPayload(
            action="HEARTBEAT",
            reason="LIVELINESS",
            metadata={"timestamp": (timestamp or datetime.now(timezone.utc)).isoformat()},
        ),
    )


class TimerService:
    """Centralized clock for the event-driven system.

    Publishes HEARTBEAT events at regular intervals to eliminate local
    polling and sleep() calls in other components.
    """

    def __init__(self, event_bus: EventBusProtocol, interval_s: float = 1.0) -> None:
        self.event_bus = event_bus
        self.interval_s = interval_s
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main heartbeat emission loop.

        This is the ONLY allowed persistent loop with sleep in the production path,
        serving as the system's global pulse.
        """
        while self._running:
            try:
                # Publish heartbeat
                await self.event_bus.publish(HeartbeatEvent())

                # Precise interval wait
                await asyncio.sleep(self.interval_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue pulse
                import logging

                logging.getLogger("qtrader.timer").error(f"Heartbeat failure: {e}")
                await asyncio.sleep(self.interval_s)
