from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from qtrader.core.events import ConfigChangeEvent, EventType

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus


class ConfigEventBus:
    """
    High-priority propagation channel for configuration changes.
    Ensures that all system modules are synchronized with the new config state.
    """

    def __init__(self, main_bus: EventBus) -> None:
        self._main_bus = main_bus
        self._subscribers: dict[str, list[Callable[[ConfigChangeEvent], Any]]] = {}

    async def publish_change(self, event: ConfigChangeEvent) -> None:
        """
        Broadcast a configuration change event to the global bus 
        and trigger local subscribers.
        """
        logger.info(
            f"[CONFIG-BUS] Publishing Change: {event.payload.config_key} "
            f"({event.payload.old_value} -> {event.payload.new_value})"
        )
        
        # 1. Global propagation
        await self._main_bus.publish(EventType.CONFIG_CHANGED, event)
        
        # 2. Local notification (Fast-path)
        key = event.payload.config_key
        # Notify subscribers to the specific key or 'all'
        for k in [key, "all"]:
            if k in self._subscribers:
                tasks = [
                    asyncio.create_task(sub(event)) 
                    for sub in self._subscribers[k]
                ]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    def subscribe(self, config_key: str, callback: Callable[[ConfigChangeEvent], Any]) -> None:
        """
        Subscribe to changes for a specific config key or 'all' keys.
        """
        if config_key not in self._subscribers:
            self._subscribers[config_key] = []
        self._subscribers[config_key].append(callback)
        logger.debug(f"[CONFIG-BUS] New subscriber for key: {config_key}")
