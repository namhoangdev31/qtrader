from __future__ import annotations

import time
from enum import Enum, auto
from typing import Any, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """Consolidated Event Types for the global event system."""
    MARKET_DATA = "MARKET_DATA"
    MARKET_DELTA = "MARKET_DELTA"
    GAP_DETECTED = "GAP_DETECTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    GAP_FREE_MARKET = "GAP_FREE_MARKET"
    FEATURE = "FEATURE"
    SIGNAL = "SIGNAL"
    ENSEMBLE_SIGNAL = "ENSEMBLE_SIGNAL"
    ORDER = "ORDER"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    FILL = "FILL"
    RISK = "RISK"
    SYSTEM = "SYSTEM"
    TRADING_HALT = "TRADING_HALT"
    DRIFT = "DRIFT"
    MODEL_RETRAIN = "MODEL_RETRAIN"
    ERROR = "ERROR"
    HEARTBEAT = "HEARTBEAT"
    CLOCK_SYNC = "CLOCK_SYNC"
    DATA_ERROR = "DATA_ERROR"
    DATA_REJECTED = "DATA_REJECTED"
    FEED_EVENT = "FEED_EVENT"
    RETRY_ORDER = "RETRY_ORDER"
    FEEDBACK_UPDATE = "FEEDBACK_UPDATE"
    NAV_UPDATED = "NAV_UPDATED"
    LEDGER_ENTRY = "LEDGER_ENTRY"
    FEE_CALCULATED = "FEE_CALCULATED"
    FUNDING_CALCULATED = "FUNDING_CALCULATED"
    CONFIG_CHANGED = "CONFIG_CHANGED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"


class MarketPayload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    symbol: str
    bid: float
    ask: float
    seq_id: int | None = None
    data: Any = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    symbol: str
    action: str  # BUY or SELL
    quantity: float
    price: float | None = None
    order_type: str = "MARKET"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str | None = None
    risk_type: str
    value: float
    threshold: float
    metrics: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeaturePayload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    symbol: str
    features: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    signal_type: str
    strength: float
    confidence: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


class FillPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: str
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: str
    message: str
    exception_type: str | None = None
    stack_trace: str | None = None
    severity: str = "ERROR"


class FeedPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str | None = None
    source: str
    latency: float


class MarketDeltaPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    seq_id: int
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


class GapPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    expected_seq: int
    received_seq: int


class RecoveryPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    recovered_seq: int


class ClockSyncPayload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    original_timestamp: Any
    normalized_timestamp: Any
    offset_ms: float


class RetryOrderPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    attempt: int
    metadata: dict[str, Any] = Field(default_factory=dict)

class NAVPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    nav: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    total_fees: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerEntryPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_id: str
    debit: float
    credit: float
    currency: str = "USD"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    symbol: str
    fee_amount: float
    currency: str = "USD"
    fee_type: str = "TAKER"
    metadata: dict[str, Any] = Field(default_factory=dict)

class FundingPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    position_size: float
    funding_rate: float
    funding_amount: float
    mark_price: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfigChangePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    config_key: str
    old_value: Any
    new_value: Any
    version: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskApprovedPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskRejectedPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    reason: str
    metric_value: float
    threshold: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseEvent(BaseModel):
    """
    Global immutable event schema.
    Guarantees compatibility across EventBus, EventStore, and ReplayEngine.
    """
    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4, description="Unique event identifier for idempotency")
    trace_id: UUID = Field(description="Correlation ID propagated across the pipeline")
    event_type: EventType = Field(description="The type of the event")
    version: int = Field(default=1, description="Schema version for backward compatibility")
    timestamp: int = Field(
        default_factory=lambda: int(time.time() * 1_000_000),
        description="Microseconds since epoch (normalized)"
    )
    source: str = Field(description="Originating module name")
    payload: Any = Field(description="Event-specific data (BaseModel or dict)")
    
    # Metadata for distributed event bus and storage
    partition_key: str | None = Field(default=None, description="Key used for deterministic routing")
    delivery_attempt: int = Field(default=1, description="Number of times this event has been attempted")
    offset: int | None = Field(default=None, description="Monotonically increasing sequence ID per partition")

    @property
    def type(self) -> EventType:
        """Backward compatibility with legacy .type attribute."""
        return self.event_type


class MarketEvent(BaseEvent):
    """Event representing a market update."""
    event_type: EventType = EventType.MARKET_DATA
    payload: MarketPayload

    @property
    def symbol(self) -> str:
        return self.payload.symbol

    @property
    def bid(self) -> float:
        return self.payload.bid

    @property
    def ask(self) -> float:
        return self.payload.ask

    @property
    def seq_id(self) -> int | None:
        return self.payload.seq_id


class OrderEvent(BaseEvent):
    """Event representing an order action."""
    event_type: EventType = EventType.ORDER
    payload: OrderPayload

    @property
    def order_id(self) -> str:
        return self.payload.order_id

    @property
    def symbol(self) -> str:
        return self.payload.symbol

    @property
    def action(self) -> str:
        return self.payload.action

    @property
    def quantity(self) -> float:
        return self.payload.quantity


class SignalEvent(BaseEvent):
    """Event representing a trading signal."""
    event_type: EventType = EventType.SIGNAL
    payload: SignalPayload

    @property
    def symbol(self) -> str:
        return self.payload.symbol

    @property
    def signal_type(self) -> str:
        return self.payload.signal_type

    @property
    def strength(self) -> float:
        return self.payload.strength

    @property
    def signal(self) -> float:
        """Compatibility with the signal calculation logic."""
        if self.payload.signal_type == "BUY":
            return self.payload.strength
        if self.payload.signal_type == "SELL":
            return -self.payload.strength
        return 0.0


class RiskEvent(BaseEvent):
    """Event representing a risk limit or violation."""
    event_type: EventType = EventType.RISK
    payload: RiskPayload

    @property
    def symbol(self) -> str | None:
        return self.payload.symbol


class FillEvent(BaseEvent):
    """Event representing an order fill."""
    event_type: EventType = EventType.FILL
    payload: FillPayload

    @property
    def order_id(self) -> str:
        return self.payload.order_id


class SystemEvent(BaseEvent):
    """Event representing system-wide actions."""
    event_type: EventType = EventType.SYSTEM
    payload: SystemPayload


class ErrorEvent(BaseEvent):
    """Event representing a system error."""
    event_type: EventType = EventType.ERROR
    payload: ErrorPayload


class MarketDeltaEvent(BaseEvent):
    event_type: EventType = EventType.MARKET_DELTA
    payload: MarketDeltaPayload


class GapDetectedEvent(BaseEvent):
    event_type: EventType = EventType.GAP_DETECTED
    payload: GapPayload


class RecoveryCompletedEvent(BaseEvent):
    event_type: EventType = EventType.RECOVERY_COMPLETED
    payload: RecoveryPayload


class GapFreeMarketEvent(BaseEvent):
    event_type: EventType = EventType.GAP_FREE_MARKET
    payload: MarketDeltaPayload

    @property
    def bid(self) -> float:
        return self.payload.bids[0][0] if self.payload.bids else 0.0

    @property
    def ask(self) -> float:
        return self.payload.asks[0][0] if self.payload.asks else 0.0


class ClockSyncEvent(BaseEvent):
    event_type: EventType = EventType.CLOCK_SYNC
    payload: ClockSyncPayload


class NAVEvent(BaseEvent):
    """Event representing a portfolio NAV update."""
    event_type: EventType = EventType.NAV_UPDATED
    payload: NAVPayload


class LedgerEntryEvent(BaseEvent):
    """Event representing a double-entry ledger record."""
    event_type: EventType = EventType.LEDGER_ENTRY
    payload: LedgerEntryPayload


class FeeEvent(BaseEvent):
    """Event representing a trading fee calculation."""
    event_type: EventType = EventType.FEE_CALCULATED
    payload: FeePayload


class FundingEvent(BaseEvent):
    """Event representing a funding rate payment."""
    event_type: EventType = EventType.FUNDING_CALCULATED
    payload: FundingPayload


class ConfigChangeEvent(BaseEvent):
    """Event representing a runtime configuration update."""
    event_type: EventType = EventType.CONFIG_CHANGED
    payload: ConfigChangePayload


class RiskApprovedEvent(BaseEvent):
    """Event representing a risk approval for an order."""
    event_type: EventType = EventType.RISK_APPROVED
    payload: RiskApprovedPayload


class RiskRejectedEvent(BaseEvent):
    """Event representing a risk rejection for an order."""
    event_type: EventType = EventType.RISK_REJECTED
    payload: RiskRejectedPayload