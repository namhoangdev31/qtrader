import asyncio
from datetime import datetime

from qtrader.core.event import Event, EventType
from qtrader.core.types import EventBusProtocol


class HeartbeatEvent(Event):
    """Periodic system heartbeat event."""
    def __init__(self, timestamp: datetime | None = None) -> None:
        super().__init__(
            type=EventType.HEARTBEAT, 
            timestamp=timestamp or datetime.utcnow()
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
                # In HFT, we might use a spin-wait if sub-ms precision is needed,
                # but for general coordination, asyncio.sleep(interval) is reactive.
                await asyncio.sleep(self.interval_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue pulse
                import logging
                logging.getLogger("qtrader.timer").error(f"Heartbeat failure: {e}")
                await asyncio.sleep(self.interval_s)
