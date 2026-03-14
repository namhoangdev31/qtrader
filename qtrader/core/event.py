"""Event type system for EventBus: market, signals, orders, fills, risk, system, heartbeat."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

__all__ = [
    "EventType",
    "Event",
    "MarketDataEvent",
    "SignalEvent",
    "OrderEvent",
    "FillEvent",
    "RiskEvent",
    "RegimeChangeEvent",
    "SystemEvent",
    "HeartbeatEvent",
]


class EventType(Enum):
    MARKET_DATA = auto()
    SIGNAL = auto()
    ORDER = auto()
    FILL = auto()
    RISK = auto()
    CLOCK = auto()
    REGIME_CHANGE = auto()  # Emitted by AutonomousLoop on regime shift
    SYSTEM = auto()  # Bot lifecycle events (start/stop/halt)
    HEARTBEAT = auto()  # Periodic liveness signal


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


@dataclass(frozen=True, kw_only=True)
class RegimeChangeEvent(Event):
    """Emitted when regime detector identifies a regime shift."""
    regime_id: int
    confidence: float  # posterior probability of current regime
    previous_regime_id: int | None = None
    type: EventType = EventType.REGIME_CHANGE


@dataclass(frozen=True, kw_only=True)
class SystemEvent(Event):
    """Bot lifecycle events: START, STOP, EMERGENCY_HALT, RETRAIN."""
    action: str  # "START" | "STOP" | "EMERGENCY_HALT" | "RETRAIN"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.SYSTEM


@dataclass(frozen=True, kw_only=True)
class HeartbeatEvent(Event):
    """Periodic liveness signal from a component."""
    source: str  # Component name ("bot_runner", "risk_engine", etc.)
    uptime_seconds: float
    type: EventType = EventType.HEARTBEAT
