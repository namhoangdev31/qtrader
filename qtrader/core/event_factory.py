from __future__ import annotations

import logging
from typing import Any, Dict, Type

from qtrader.core.events import (
    BaseEvent,
    ClockSyncEvent,
    ConfigChangeEvent,
    ErrorEvent,
    EventType,
    FeaturePayload,
    FeeEvent,
    FillEvent,
    FundingEvent,
    GapDetectedEvent,
    GapFreeMarketEvent,
    MarketDeltaEvent,
    MarketEvent,
    NAVEvent,
    LedgerEntryEvent,
    OrderEvent,
    RecoveryCompletedEvent,
    RiskApprovedEvent,
    RiskEvent,
    RiskRejectedEvent,
    SignalEvent,
    SystemEvent,
)

logger = logging.getLogger(__name__)


class EventFactory:
    """
    Factory for polymorphic event deserialization.
    Maps EventType to specific Pydantic event classes.
    """

    # Mapping of EventType to its corresponding Pydantic class
    _TYPE_MAP: Dict[EventType, Type[BaseEvent]] = {
        EventType.MARKET_DATA: MarketEvent,
        EventType.MARKET_DELTA: MarketDeltaEvent,
        EventType.GAP_DETECTED: GapDetectedEvent,
        EventType.RECOVERY_COMPLETED: RecoveryCompletedEvent,
        EventType.GAP_FREE_MARKET: GapFreeMarketEvent,
        EventType.SIGNAL: SignalEvent,
        EventType.ORDER: OrderEvent,
        EventType.ORDER_CREATED: OrderEvent,  # Map legacy types if needed
        EventType.ORDER_FILLED: FillEvent,    # Map legacy types if needed
        EventType.FILL: FillEvent,
        EventType.RISK: RiskEvent,
        EventType.SYSTEM: SystemEvent,
        EventType.ERROR: ErrorEvent,
        EventType.CLOCK_SYNC: ClockSyncEvent,
        EventType.NAV_UPDATED: NAVEvent,
        EventType.LEDGER_ENTRY: LedgerEntryEvent,
        EventType.FEE_CALCULATED: FeeEvent,
        EventType.FUNDING_CALCULATED: FundingEvent,
        EventType.CONFIG_CHANGED: ConfigChangeEvent,
        EventType.RISK_APPROVED: RiskApprovedEvent,
        EventType.RISK_REJECTED: RiskRejectedEvent,
    }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseEvent:
        """
        Reconstruct a specialized event object from a raw dictionary.
        
        Args:
            data: The raw event data (usually from JSON).
            
        Returns:
            BaseEvent: An instance of the correct specialized event subclass.
        """
        event_type_str = data.get("event_type")
        if not event_type_str:
            # Fallback for legacy events
            event_type_str = data.get("type")
            
        if not event_type_str:
            raise ValueError("Missing 'event_type' or 'type' in event data")

        try:
            event_type = EventType(event_type_str)
            event_class = cls._TYPE_MAP.get(event_type, BaseEvent)
            return event_class.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to deserialize event of type {event_type_str}: {e}")
            # Fallback to BaseEvent if specific mapping fails but data matches schema
            return BaseEvent.model_validate(data)
