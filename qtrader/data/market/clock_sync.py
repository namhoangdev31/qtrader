from __future__ import annotations

import asyncio
import datetime
import time
import uuid
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.event import EventType, NormalizedTimestampEvent

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.oms.event_store import EventStore


class ClockSync:
    """Engine for global clock synchronization and drift tracking.
    
    TREF (Time Reference) = T_local + Offset
    Offset = T_exchange - T_local
    
    This stage ensures all events enter the pipeline with a normalized, 
    latency-aware timestamp.
    """

    def __init__(
        self, 
        event_store: EventStore, 
        event_bus: EventBus | None = None,
        ntp_server: str = "pool.ntp.org",
        update_interval: int = 3600
    ) -> None:
        self.event_store = event_store
        self.event_bus = event_bus
        self.ntp_server = ntp_server
        self.update_interval = update_interval
        
        self._offset_ms: float = 0.0
        self._last_sync_ts: float = 0.0
        self._is_running = False
        self._sync_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background synchronization loop."""
        if self._is_running:
            return
        self._is_running = True
        logger.info(
            f"ClockSync: Started with server {self.ntp_server} "
            f"(interval {self.update_interval}s)"
        )
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def stop(self) -> None:
        """Stop the clock synchronization loop."""
        self._is_running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("ClockSync: Stopped.")

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply the current drift offset to an incoming event's timestamp.
        
        Args:
            event: Raw event dict.
            
        Returns:
            The event with `normalized_timestamp` and `clock_offset_ms` added.
        """
        raw_ts = event.get("timestamp", time.time())
        # Apply offset: T_normalized = T_exchange_estimate
        event["normalized_timestamp"] = raw_ts + (self._offset_ms / 1000.0)
        event["clock_offset_ms"] = self._offset_ms
        return event

    async def update_offset(self) -> float:
        """Force a manual offset update against the reference server."""
        try:
            # In a production system, this would use ntplib or a PTP hardware clock.
            # We simulate the NTP offset calculation: T_ref - T_local
            new_offset = await self._get_ntp_offset()
            
            # Smoothing/Validation: Institutional systems usually use a Kalman Filter here,
            # but here the user specifies |offset| < 1ms as a constraint for the model.
            # We'll log it if it's large.
            if abs(new_offset - self._offset_ms) > 1.0:
                 logger.warning(
                     f"ClockSync: Significant drift detected: {new_offset:.3f}ms "
                     f"(was {self._offset_ms:.3f}ms)"
                 )
            
            self._offset_ms = new_offset
            self._last_sync_ts = time.time()
            
            # Record the synchronization event for audit logs
            await self._record_sync()
            
            return self._offset_ms
        except Exception as e:
            logger.error(f"ClockSync: Failed to update offset: {e}")
            return self._offset_ms

    async def _sync_loop(self) -> None:
        """Periodic synchronization background task."""
        while self._is_running:
            await self.update_offset()
            await asyncio.sleep(self.update_interval)

    async def _get_ntp_offset(self) -> float:
        """Simulate NTP offset calculation (T_reference - T_local)."""
        # Simulated drift of 2.5ms
        await asyncio.sleep(0.05) # Simulate network roundtrip
        return 2.5 

    async def _record_sync(self) -> None:
        """Record the NormalizedTimestampEvent to the EventStore and Bus."""
        now = datetime.datetime.now(datetime.timezone.utc)
        normalized_now = now + datetime.timedelta(milliseconds=self._offset_ms)
        
        sync_event = NormalizedTimestampEvent(
            event_id=str(uuid.uuid4()),
            timestamp=now,
            original_timestamp=now,
            normalized_timestamp=normalized_now,
            offset_ms=self._offset_ms
        )
        
        # Persistence for audit trail
        await self.event_store.record_event(sync_event)
        
        # Real-time update for downstream monitors
        if self.event_bus:
            await self.event_bus.publish(EventType.CLOCK_SYNC, sync_event)
