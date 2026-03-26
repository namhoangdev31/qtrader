from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl


class EventType(Enum):
    MARKET_DATA = auto()
    FEATURE = auto()
    SIGNAL = auto()
    ENSEMBLE_SIGNAL = auto()
    ORDER = auto()
    FILL = auto()
    RISK = auto()
    SYSTEM = auto()
    FEEDBACK_UPDATE = auto()
    RETRY_ORDER = auto()
    DRIFT = auto()
    MODEL_RETRAIN = auto()
    ERROR = auto()
    DATA_ERROR = auto()
    HEARTBEAT = auto()
    ORDER_CREATED = auto()
    ORDER_FILLED = auto()
    ORDER_REJECTED = auto()
    TRADING_HALT = auto()
    FEED_EVENT = auto()
    MARKET_DELTA = auto()
    GAP_DETECTED = auto()
    RECOVERY_COMPLETED = auto()
    GAP_FREE_MARKET = auto()
    CLOCK_SYNC = auto()
    DATA_REJECTED = auto()


@dataclass(frozen=True, kw_only=True)
class Event:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    trace_id: str = field(default_factory=lambda: "pending")


@dataclass(frozen=True, kw_only=True)
class FeedEvent(Event):
    event_id: str
    source: str  # e.g., 'Feed A', 'Feed B'
    latency: float  # in ms
    type: EventType = EventType.FEED_EVENT


@dataclass(frozen=True, kw_only=True)
class MarketDeltaEvent(Event):
    symbol: str
    seq_id: int
    bids: list[tuple[float, float]]  # [price, quantity]
    asks: list[tuple[float, float]]  # [price, quantity]
    type: EventType = EventType.MARKET_DELTA


@dataclass(frozen=True, kw_only=True)
class GapDetectedEvent(Event):
    event_id: str
    symbol: str
    expected_seq: int
    received_seq: int
    type: EventType = EventType.GAP_DETECTED


@dataclass(frozen=True, kw_only=True)
class RecoveryCompletedEvent(Event):
    event_id: str
    symbol: str
    recovered_seq: int
    type: EventType = EventType.RECOVERY_COMPLETED


@dataclass(frozen=True, kw_only=True)
class GapFreeMarketEvent(Event):
    symbol: str
    seq_id: int
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    type: EventType = EventType.GAP_FREE_MARKET

    @property
    def bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def ask(self) -> float:
        return self.asks[0][0] if self.asks else 0.0


@dataclass(frozen=True, kw_only=True)
class NormalizedTimestampEvent(Event):
    original_timestamp: datetime.datetime
    normalized_timestamp: datetime.datetime
    offset_ms: float
    type: EventType = EventType.CLOCK_SYNC


@dataclass(frozen=True, kw_only=True)
class DataErrorEvent(Event):
    symbol: str
    reason: str
    type: EventType = EventType.DATA_ERROR


@dataclass(frozen=True, kw_only=True)
class DataRejectedEvent(Event):
    symbol: str
    reason: str
    value: float
    threshold: float
    type: EventType = EventType.DATA_REJECTED


@dataclass(frozen=True, kw_only=True)
class MarketDataEvent(Event):
    symbol: str
    seq_id: int | None = None
    data: pl.DataFrame | dict[str, Any]  # Can be OHLCV DataFrame or Tick dict
    metadata: dict[str, Any] | None = None
    type: EventType = EventType.MARKET_DATA

    @property
    def bid(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("bid", 0.0))
        return 0.0

    @property
    def ask(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("ask", 0.0))
        return 0.0

    @property
    def price(self) -> float:
        """Alias for close price for backward compatibility."""
        return self.close

    @property
    def close(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("close") or self.data.get("last_price") or 0.0)
        return 0.0

    @property
    def open(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("open") or 0.0)
        return 0.0

    @property
    def high(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("high") or 0.0)
        return 0.0

    @property
    def low(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("low") or 0.0)
        return 0.0

    @property
    def volume(self) -> float:
        if isinstance(self.data, dict):
            return float(self.data.get("volume") or 0.0)
        return 0.0


@dataclass(frozen=True, kw_only=True)
class FeatureEvent(Event):
    symbol: str
    features: dict[str, pl.Series]  # feature name -> series
    metadata: dict[str, Any] | None = None
    type: EventType = EventType.FEATURE


@dataclass(frozen=True, kw_only=True)
class SignalEvent(Event):
    symbol: str
    signal_type: str  # e.g., 'BUY', 'SELL', 'HOLD'
    strength: float  # Signal strength in [0, 1]
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.SIGNAL

    @property
    def signal(self) -> float:
        # Compatibility with the [GLOBAL_EVENT_DRIVEN_MIGRATION] contract
        if self.signal_type == "BUY":
            return self.strength
        if self.signal_type == "SELL":
            return -self.strength
        return 0.0

    @property
    def confidence(self) -> float:
        return self.metadata.get("confidence", 0.5)


@dataclass(frozen=True, kw_only=True)
class EnsembleSignalEvent(Event):
    symbol: str
    signal_type: str  # e.g., 'ENSEMBLE'
    strength: float  # Signal strength in [0, 1]
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.ENSEMBLE_SIGNAL


@dataclass(frozen=True, kw_only=True)
class OrderEvent(Event):
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str  # e.g., 'MARKET', 'LIMIT', 'TWAP', 'VWAP'
    quantity: float
    price: float | None = None  # For limit orders
    metadata: dict[str, Any] | None = None
    type: EventType = EventType.ORDER

    @property
    def action(self) -> str:
        return self.side


@dataclass(frozen=True, kw_only=True)
class FillEvent(Event):
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: float
    price: float
    commission: float = 0.0
    metadata: dict[str, Any] | None = None
    type: EventType = EventType.FILL


@dataclass(frozen=True, kw_only=True)
class RiskEvent(Event):
    symbol: str
    metrics: dict[str, float]  # e.g., {'var': 0.05, 'drawdown': 0.02}
    metadata: dict[str, Any] | None = None
    type: EventType = EventType.RISK


@dataclass(frozen=True, kw_only=True)
class SystemEvent(Event):
    action: str  # e.g., 'START', 'STOP', 'KILL_SWITCH'
    reason: str = ""
    metadata: dict[str, Any] | None = None
    type: EventType = EventType.SYSTEM


@dataclass(frozen=True, kw_only=True)
class RetryOrderEvent(Event):
    order: OrderEvent
    attempt: int
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.RETRY_ORDER


@dataclass(frozen=True, kw_only=True)
class DriftEvent(Event):
    symbol: str
    drift_score: float
    features: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.DRIFT


@dataclass(frozen=True, kw_only=True)
class ModelRetrainEvent(Event):
    symbol: str
    model_id: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.MODEL_RETRAIN


@dataclass(frozen=True, kw_only=True)
class ErrorEvent(Event):
    source: str
    message: str
    exception_type: str | None = None
    stack_trace: str | None = None
    severity: str = "ERROR" # INFO, WARNING, ERROR, CRITICAL
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.ERROR


@dataclass(frozen=True, kw_only=True)
class OrderCreatedEvent(Event):
    order: OrderEvent
    type: EventType = EventType.ORDER_CREATED


@dataclass(frozen=True, kw_only=True)
class OrderFilledEvent(Event):
    order_id: str
    symbol: str
    quantity: float
    price: float
    side: str
    remaining: float
    type: EventType = EventType.ORDER_FILLED


@dataclass(frozen=True, kw_only=True)
class TradingHaltEvent(Event):
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.TRADING_HALT


@dataclass(frozen=True, kw_only=True)
class OrderRejectedEvent(Event):
    order_id: str
    reason: str
    type: EventType = EventType.ORDER_REJECTED