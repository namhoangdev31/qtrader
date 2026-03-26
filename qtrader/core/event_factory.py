from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from qtrader.core.events import (
    BaseEvent,
    EventType,
)
from qtrader.core.event_validator import EventValidator, SchemaError


class EventFactory:
    """
    Factory for standardized, idempotent, and trace-propagated events.
    Enforces a strict global event schema across the system.
    """

    def __init__(self, source: str):
        """
        Initialize the factory with a fixed source module name.
        
        Args:
            source: The name of the module that will produce events.
        """
        self.source = source

    def create(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        trace_id: UUID | str | None = None,
        version: int = 1
    ) -> BaseEvent:
        """
        Create a new BaseEvent with standardized metadata and strict validation.
        
        Args:
            event_type: The type of the event.
            payload: The event-specific data.
            trace_id: A trace ID for propagation. If None, generates a new one.
            version: The schema version.
            
        Returns:
            BaseEvent: The newly created, validated event instance.
            
        Raises:
            SchemaError: If the payload fails validation for the given event type.
        """
        # Ensure trace_id is a UUID
        if isinstance(trace_id, str):
            tid = UUID(trace_id)
        elif isinstance(trace_id, UUID):
            tid = trace_id
        else:
            tid = uuid4()

        # Build the event instance
        event = BaseEvent(
            event_id=uuid4(),
            trace_id=tid,
            event_type=event_type,
            version=version,
            timestamp=int(time.time() * 1_000_000),
            source=self.source,
            payload=payload,
        )

        # Trigger validation layer
        EventValidator.validate(event)

        return event

    @staticmethod
    def from_dict(data: dict[str, Any]) -> BaseEvent:
        """
        Reconstruct an event from a dictionary (e.g., from EventStore or EventBus).
        Useful for deterministic replay and state recovery.
        """
        event = BaseEvent.model_validate(data)
        EventValidator.validate(event)
        return event
