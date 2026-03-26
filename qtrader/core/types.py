from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from qtrader.core.event import (
    EventType,
    FillEvent,
    OrderEvent,
    SignalEvent,
)

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

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
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class AlphaOutput:
    """Output from alpha generation."""
    symbol: str
    timestamp: datetime
    alpha_values: dict[str, Decimal]  # alpha name -> value
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class ValidatedFeatures:
    """Features that have passed validation."""
    symbol: str
    timestamp: datetime
    features: dict[str, Decimal]
    validation_metadata: dict[str, Any]
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class AllocationWeights:
    """Portfolio allocation weights."""
    timestamp: datetime
    weights: dict[str, Decimal]  # symbol -> weight (should sum to 1.0 or less)
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class RiskMetrics:
    """Risk metrics for a portfolio or position."""
    timestamp: datetime
    portfolio_var: Decimal  # Value at Risk
    portfolio_volatility: Decimal
    max_drawdown: Decimal
    leverage: Decimal
    trace_id: str
    metadata: dict[str, Any] | None = None


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