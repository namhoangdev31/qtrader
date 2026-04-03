"""Legacy event bus module. Deprecated in favor of qtrader.core.event_bus."""

from qtrader.core.events import BaseEvent
from qtrader.core.event_bus import EventBus as ProductionEventBus


class EventBus(ProductionEventBus):
    """Compatibility wrapper for the legacy EventBus."""

    async def publish(self, event: BaseEvent) -> None:
        # Legacy bus took a single 'event' object; new bus takes (type, data)
        await super().publish(event.event_type, event)
