from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol


from qtrader.core.event import (
    EventType,
    Event,
    MarketDataEvent,
    FeatureEvent,
    SignalEvent,
    EnsembleSignalEvent,
    OrderEvent,
    FillEvent,
    RiskEvent,
    SystemEvent,
)

# Aliases for compatibility
Signal = SignalEvent
Order = OrderEvent
Fill = FillEvent

class Side:
    """Side of an order or signal."""
    BUY = "BUY"
    SELL = "SELL"
    Buy = "BUY"  # Compatibility with lowercase/PascalCase tests
    Sell = "SELL"
    HOLD = "HOLD"


@dataclass
class MarketData:
    """Market data tick."""
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AlphaOutput:
    """Output from alpha generation."""
    symbol: str
    timestamp: datetime
    alpha_values: Dict[str, Decimal]  # alpha name -> value
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ValidatedFeatures:
    """Features that have passed validation."""
    symbol: str
    timestamp: datetime
    features: Dict[str, Decimal]
    validation_metadata: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AllocationWeights:
    """Portfolio allocation weights."""
    timestamp: datetime
    weights: Dict[str, Decimal]  # symbol -> weight (should sum to 1.0 or less)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class RiskMetrics:
    """Risk metrics for a portfolio or position."""
    timestamp: datetime
    portfolio_var: Decimal  # Value at Risk
    portfolio_volatility: Decimal
    max_drawdown: Decimal
    leverage: Decimal
    metadata: Optional[Dict[str, Any]] = None


# Protocol definitions for dependency injection
class LoggerProtocol(Protocol):
    def info(self, message: str, **kwargs: Any) -> None: ...
    def warning(self, message: str, **kwargs: Any) -> None: ...
    def error(self, message: str, **kwargs: Any) -> None: ...
    def debug(self, message: str, **kwargs: Any) -> None: ...
    def critical(self, message: str, **kwargs: Any) -> None: ...


class ConfigProtocol(Protocol):
    def __getattr__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> None: ...


class EventBusProtocol(Protocol):
    async def publish(self, event_type: EventType, data: Any) -> None: ...
    def subscribe(self, event_type: EventType, callback: Any) -> None: ...
    def unsubscribe(self, event_type: EventType, callback: Any) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...