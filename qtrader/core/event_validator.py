from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError, BaseModel

from qtrader.core.events import (
    BaseEvent,
    EventType,
    MarketPayload,
    OrderPayload,
    RiskPayload,
    FeaturePayload,
    SignalPayload,
    FillPayload,
    SystemPayload,
    ErrorPayload,
    FeedPayload,
    MarketDeltaPayload,
    GapPayload,
    RecoveryPayload,
    ClockSyncPayload,
    RetryOrderPayload,
)

logger = logging.getLogger(__name__)


class SchemaError(Exception):
    """Raised when an event fails schema validation."""


class EventValidator:
    """
    Validation layer for the global event system.
    Ensures events comply with their specific payload schemas before propagation.
    """

    @staticmethod
    def validate(event: BaseEvent) -> bool:
        """
        Validate an event against its schema and payload requirements.
        
        Args:
            event: The event instance to validate.
            
        Returns:
            bool: True if valid.
            
        Raises:
            SchemaError: If validation fails.
        """
        try:
            # 1. Base validation
            if not event.event_id or not event.trace_id:
                raise SchemaError("Missing event_id or trace_id")

            # 2. Payload-specific validation
            EventValidator.validate_payload(event.event_type, event.payload)
                
            return True

        except (ValidationError, ValueError, KeyError, SchemaError) as e:
            logger.error(f"Event validation failed: {e} | Event: {event.event_id}")
            raise SchemaError(f"Invalid schema for {event.event_type}: {e}") from e

    @staticmethod
    def validate_payload(event_type: EventType, payload: dict[str, Any] | BaseModel) -> bool:
        """Helper to validate a raw payload before event creation."""
        try:
            mapping = {
                EventType.MARKET_DATA: MarketPayload,
                EventType.ORDER: OrderPayload,
                EventType.RISK: RiskPayload,
                EventType.FEATURE: FeaturePayload,
                EventType.SIGNAL: SignalPayload,
                EventType.FILL: FillPayload,
                EventType.SYSTEM: SystemPayload,
                EventType.ERROR: ErrorPayload,
                EventType.FEED_EVENT: FeedPayload,
                EventType.MARKET_DELTA: MarketDeltaPayload,
                EventType.GAP_DETECTED: GapPayload,
                EventType.RECOVERY_COMPLETED: RecoveryPayload,
                EventType.GAP_FREE_MARKET: MarketDeltaPayload,
                EventType.CLOCK_SYNC: ClockSyncPayload,
                EventType.RETRY_ORDER: RetryOrderPayload,
            }
            
            if event_type in mapping:
                model = mapping[event_type]
                if not isinstance(payload, model):
                    model.model_validate(payload)
            return True
        except ValidationError as e:
            raise SchemaError(f"Payload validation failed for {event_type}: {e}") from e
