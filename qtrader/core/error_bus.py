"""Centralized Error Bus for unified system-wide error publishing and propagation."""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import TYPE_CHECKING, Any

from qtrader.core.event import ErrorEvent, EventType

if TYPE_CHECKING:
    from qtrader.core.bus import EventBus


class ErrorBus:
    """
    High-priority error propagation bus.
    Ensures that errors from all layers (Data, Bot, Execution, Monitoring) 
    are published to a central location for auditing and emergency response.
    """

    def __init__(self, main_bus: EventBus | None = None) -> None:
        """
        Args:
            main_bus: The global system EventBus for downstream subscriber notifications.
        """
        self._main_bus = main_bus
        self._logger = logging.getLogger("qtrader.error_bus")

    async def publish(
        self, 
        source: str, 
        message: str, 
        exception: Exception | None = None, 
        severity: str = "ERROR",
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Central point for publishing errors. 
        Automatically captures stack traces when an exception is provided.
        
        Args:
            source: The component name or layer where the error originated.
            message: A human-readable error description.
            exception: Optional Exception object for deep diagnosis.
            severity: ERROR (default), WARNING, or CRITICAL.
            metadata: Additional context for debugging.
        """
        stack_trace = None
        if exception:
            stack_trace = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))

        event = ErrorEvent(
            source=source,
            message=message,
            exception_type=type(exception).__name__ if exception else None,
            stack_trace=stack_trace,
            severity=severity,
            metadata=metadata or {}
        )

        # 1. Immediate Logging
        log_msg = f"[{source}] {message}"
        if severity == "CRITICAL":
            self._logger.error(f"!!! CRITICAL: {log_msg}")
        elif severity == "WARNING":
            self._logger.warning(log_msg)
        else:
            self._logger.error(log_msg)

        # 2. EventBus Propagation (if available)
        if self._main_bus:
            # Note: ErrorEvents are high-priority but we use the main bus for centralized handling
            await self._main_bus.publish(EventType.ERROR, event)
        
    async def capture_exception(self, source: str, exception: Exception, message: str = "Unhandled exception") -> None:
        """Convenience method to capture and publish a full exception."""
        await self.publish(source, message, exception=exception, severity="ERROR")
