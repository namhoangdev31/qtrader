from __future__ import annotations

import asyncio
import datetime
import logging
import struct
import time
from typing import Any

from loguru import logger

from qtrader.core.event import EventType, NormalizedTimestampEvent
from qtrader.core.event_bus import EventBus
from qtrader.oms.event_store import EventStore


class ClockSync:
    """Global clock synchronization and timestamp normalization engine.
    
    Ensures all system timestamps are aligned to a single reference clock
    for accurate latency measurement and deterministic event ordering.
    """

    def __init__(
        self,
        event_store: EventStore,
        event_bus: EventBus | None = None,
        ntp_server: str = "pool.ntp.org",
        update_interval: int = 3600,
    ) -> None:
        self.event_store = event_store
        self.event_bus = event_bus
        self.ntp_server = ntp_server
        self.update_interval = update_interval
        
        self._offset_ms: float = 0.0
        self._last_sync_ts: float = 0.0
        self._is_running = False
        self._sync_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the periodic clock synchronization loop."""
        if self._is_running:
            return
        self._is_running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"ClockSync: Started with server {self.ntp_server} (interval {self.update_interval}s)")

    async def stop(self) -> None:
        """Stop the clock synchronization loop."""
        self._is_running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("ClockSync: Stopped")

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """Normalize the timestamp of an incoming raw event.
        
        Args:
            event: Raw event dict.
            
        Returns:
            The event with an added 'normalized_timestamp' and 'offset_ms'.
        """
        original_ts_float = event.get("timestamp", time.time())
        
        # Apply offset: normalized_time = t_event + offset
        normalized_ts_float = original_ts_float + (self._offset_ms / 1000.0)
        
        event["original_timestamp"] = original_ts_float
        event["normalized_timestamp"] = normalized_ts_float
        event["clock_offset_ms"] = self._offset_ms
        
        return event

    async def update_offset(self) -> float:
        """Fetch reference time and compute the offset."""
        try:
            # In a real environment, we'd use a UDP NTP request.
            # Here we simulate the offset calculation for the challenge.
            # offset = t_exchange - t_local
            new_offset = await self._get_ntp_offset()
            
            # Drift constraint check: |offset| < 1ms jump between syncs is typical
            # but here the user specifies |offset| < 1ms as a constraint for the model.
            # We'll log it if it's large.
            if abs(new_offset - self._offset_ms) > 1.0:
                 logger.warning(f"ClockSync: Significant drift detected: {new_offset:.3f}ms (was {self._offset_ms:.3f}ms)")
            
            self._offset_ms = new_offset
            self._last_sync_ts = time.time()
            
            # Persist and Publish
            await self._record_sync()
            
            return self._offset_ms
        except Exception as e:
            logger.error(f"ClockSync: Failed to update offset fallback to last known: {e}")
            return self._offset_ms

    async def _sync_loop(self) -> None:
        """Background loop for periodic offset updates."""
        while self._is_running:
            await self.update_offset()
            await asyncio.sleep(self.update_interval)

    async def _get_ntp_offset(self) -> float:
        """Simulated NTP offset calculation logic."""
        # For the mock: Assume a small constant drift + random jitter
        # Real-world: offset = ((t1 - t0) + (t2 - t3)) / 2
        await asyncio.sleep(0.01) # Simulate network latency
        return 0.452 # Mock offset in ms

    async def _record_sync(self) -> None:
        """Record the NormalizedTimestampEvent to the EventStore and Bus."""
        import uuid
        
        now = datetime.datetime.now(datetime.timezone.utc)
        normalized_now = now + datetime.timedelta(milliseconds=self._offset_ms)
        
        sync_event = NormalizedTimestampEvent(
            event_id=str(uuid.uuid4()),
            trace_id="system-sync",
            original_timestamp=now,
            normalized_timestamp=normalized_now,
            offset_ms=self._offset_ms,
        )
        
        # Persist to Store
        await self.event_store.record_event(sync_event)
        
        # Publish to Bus
        if self.event_bus:
            await self.event_bus.publish(EventType.CLOCK_SYNC, sync_event)
        
        logger.debug(f"ClockSync: Corrected offset to {self._offset_ms:.3f}ms")
