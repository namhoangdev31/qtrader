from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional

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


@dataclass(frozen=True, kw_only=True)
class Event:
    type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True, kw_only=True)
class MarketDataEvent(Event):
    symbol: str
    data: pl.DataFrame  # Expected to have OHLCV columns
    metadata: Optional[Dict[str, Any]] = None
    type: EventType = EventType.MARKET_DATA


@dataclass(frozen=True, kw_only=True)
class FeatureEvent(Event):
    symbol: str
    features: Dict[str, pl.Series]  # feature name -> series
    metadata: Optional[Dict[str, Any]] = None
    type: EventType = EventType.FEATURE


@dataclass(frozen=True, kw_only=True)
class SignalEvent(Event):
    symbol: str
    signal_type: str  # e.g., 'BUY', 'SELL', 'HOLD'
    strength: float  # Signal strength in [0, 1]
    metadata: Dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.SIGNAL


@dataclass(frozen=True, kw_only=True)
class EnsembleSignalEvent(Event):
    symbol: str
    signal_type: str  # e.g., 'ENSEMBLE'
    strength: float  # Signal strength in [0, 1]
    metadata: Dict[str, Any] = field(default_factory=dict)
    type: EventType = EventType.ENSEMBLE_SIGNAL


@dataclass(frozen=True, kw_only=True)
class OrderEvent(Event):
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str  # e.g., 'MARKET', 'LIMIT', 'TWAP', 'VWAP'
    quantity: float
    price: Optional[float] = None  # For limit orders
    metadata: Optional[Dict[str, Any]] = None
    type: EventType = EventType.ORDER


@dataclass(frozen=True, kw_only=True)
class FillEvent(Event):
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: float
    price: float
    commission: float = 0.0
    metadata: Optional[Dict[str, Any]] = None
    type: EventType = EventType.FILL


@dataclass(frozen=True, kw_only=True)
class RiskEvent(Event):
    symbol: str
    metrics: Dict[str, float]  # e.g., {'var': 0.05, 'drawdown': 0.02}
    metadata: Optional[Dict[str, Any]] = None
    type: EventType = EventType.RISK


@dataclass(frozen=True, kw_only=True)
class SystemEvent(Event):
    action: str  # e.g., 'START', 'STOP', 'KILL_SWITCH'
    reason: str = ""
    metadata: Optional[Dict[str, Any]] = None
    type: EventType = EventType.SYSTEM