import logging
from typing import Any
import asyncio

from qtrader.core.event import ErrorEvent, EventType
from qtrader.core.event_bus import EventBus

logger = logging.getLogger(__name__)

class AlertSystem:
    """
    Global Alert System.
    Provides no-silent-failure alert routing.
    """
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.alerts_sent: list[ErrorEvent] = []
        self._running = False
        
    async def start(self) -> None:
        self.event_bus.subscribe(EventType.ERROR, self._on_error)
        self._running = True
        logger.info("AlertSystem initialized and subscribed to ERROR events.")
        
    async def _on_error(self, event: ErrorEvent) -> None:
        """Process incoming ErrorEvents and route them."""
        # Only route HIGH or CRITICAL severity to physical alerts (simulated here)
        if event.severity in ("HIGH", "CRITICAL"):
            await self._route_alert(event)
            
    async def _route_alert(self, event: ErrorEvent) -> None:
        """Route alert to PagerDuty/Slack/Email (simulated)."""
        logger.critical(f"ALERT SENT: {event.severity} [{event.source}] {event.message}")
        # In a real system, POST to webhook here
        self.alerts_sent.append(event)
        
    def get_sent_alerts(self) -> list[ErrorEvent]:
        return self.alerts_sent
