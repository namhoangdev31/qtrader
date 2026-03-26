from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qtrader.core.events import (
    BaseEvent,
    EventType,
    MarketEvent,
    SignalEvent,
    OrderEvent,
    FillEvent,
    RiskEvent,
    SystemEvent,
    ErrorEvent,
    MarketDeltaEvent,
    GapDetectedEvent,
    RecoveryCompletedEvent,
    GapFreeMarketEvent,
    ClockSyncEvent,
)

if TYPE_CHECKING:
    import polars as pl

Event = BaseEvent
MarketDataEvent = MarketEvent
FeatureEvent = BaseEvent
EnsembleSignalEvent = SignalEvent
RetryOrderEvent = BaseEvent
DriftEvent = BaseEvent
ModelRetrainEvent = BaseEvent
OrderCreatedEvent = OrderEvent
OrderFilledEvent = FillEvent
OrderRejectedEvent = BaseEvent
TradingHaltEvent = SystemEvent
NormalizedTimestampEvent = ClockSyncEvent


class FeedEvent(BaseEvent):
    """Bridge shim for FeedEvent if needed."""
    pass


# Re-export EventType members for compatibility
class CompatibilityEventType:
    MARKET_DATA = EventType.MARKET_DATA
    MARKET_DELTA = EventType.MARKET_DELTA
    GAP_DETECTED = EventType.GAP_DETECTED
    RECOVERY_COMPLETED = EventType.RECOVERY_COMPLETED
    GAP_FREE_MARKET = EventType.GAP_FREE_MARKET
    FEATURE = EventType.FEATURE
    SIGNAL = EventType.SIGNAL
    ENSEMBLE_SIGNAL = EventType.ENSEMBLE_SIGNAL
    ORDER = EventType.ORDER
    ORDER_CREATED = EventType.ORDER_CREATED
    ORDER_FILLED = EventType.ORDER_FILLED
    ORDER_REJECTED = EventType.ORDER_REJECTED
    FILL = EventType.FILL
    RISK = EventType.RISK
    SYSTEM = EventType.SYSTEM
    TRADING_HALT = EventType.TRADING_HALT
    DRIFT = EventType.DRIFT
    MODEL_RETRAIN = EventType.MODEL_RETRAIN
    ERROR = EventType.ERROR
    HEARTBEAT = EventType.HEARTBEAT
    CLOCK_SYNC = EventType.CLOCK_SYNC
    DATA_ERROR = EventType.DATA_ERROR
    DATA_REJECTED = EventType.DATA_REJECTED
    FEED_EVENT = EventType.FEED_EVENT
    RETRY_ORDER = EventType.RETRY_ORDER
    FEEDBACK_UPDATE = EventType.FEEDBACK_UPDATE