from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    MARKET_DATA = auto()
    SIGNAL = auto()
    ORDER = auto()
    FILL = auto()
    RISK = auto()
    CLOCK = auto()


@dataclass(frozen=True, kw_only=True)
class Event:
    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, kw_only=True)
class MarketDataEvent(Event):
    symbol: str
    data: dict[str, Any]
    type: EventType = EventType.MARKET_DATA


@dataclass(frozen=True, kw_only=True)
class SignalEvent(Event):
    symbol: str
    signal_type: str  # e.g., "LONG", "SHORT", "EXIT"
    strength: float
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.SIGNAL


@dataclass(frozen=True, kw_only=True)
class OrderEvent(Event):
    symbol: str
    order_type: str
    quantity: float
    price: float | None = None
    side: str = "BUY"  # or "SELL"
    order_id: str | None = None
    type: EventType = EventType.ORDER


@dataclass(frozen=True, kw_only=True)
class FillEvent(Event):
    symbol: str
    quantity: float
    price: float
    commission: float
    side: str
    order_id: str
    fill_id: str
    type: EventType = EventType.FILL


@dataclass(frozen=True, kw_only=True)
class RiskEvent(Event):
    reason: str
    action: str  # e.g., "BLOCK", "LIQUIDATE"
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.RISK
