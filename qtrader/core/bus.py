"""Legacy event bus module. Deprecated in favor of qtrader.core.event_bus."""

from qtrader.core.event_bus import EventBus as ProductionEventBus
from qtrader.core.events import BaseEvent


class EventBus(ProductionEventBus):
    """Compatibility wrapper for the legacy EventBus."""

    async def publish(self, event: BaseEvent) -> bool:
        # Legacy bus took a single 'event' object; new bus takes (event)
        # We ensure it returns bool for protocol compatibility.
        return await super().publish(event)
