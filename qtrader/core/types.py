from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from qtrader.core.events import (
    BaseEvent,
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


@dataclass
class IngestionTrace:
    """Forensic trace for the ingestion stage."""

    price: float
    volatility: float
    spread_bps: float
    is_live: bool
    timestamp: str


@dataclass
class AlphaTrace:
    """Forensic trace for the alpha stage."""

    model_name: str
    action: str
    confidence: float
    indicators: dict[str, float]  # e.g., {"rsi": 65.2, "sma_delta": 1.5}
    forecast: list[float] | None = None
    reasoning: str | None = None


@dataclass
class RiskTrace:
    """Forensic trace for the risk stage."""

    initial_stop_loss: float
    initial_take_profit: float
    adjusted_stop_loss: float
    adjusted_take_profit: float
    position_size_pct: float
    notional_usd: float
    risk_score: float


@dataclass
class ExecutionTrace:
    """Forensic trace for the execution stage."""

    order_id: str
    fill_price: float
    slippage_bps: float
    fee_usd: float
    status: str


@dataclass
class PipelineTrace:
    """Complete forensic trace of a single pipeline pulse."""

    trace_id: str
    timestamp: str
    ingestion: IngestionTrace | None = None
    alpha: AlphaTrace | None = None
    risk: RiskTrace | None = None
    execution: ExecutionTrace | None = None
    module_traces: dict[str, Any] | None = None  # Registry for all core components


class EventBusProtocol(Protocol):
    async def publish(self, event: BaseEvent) -> bool: ...
    def subscribe(self, event_type: EventType, callback: Any) -> None: ...
    def unsubscribe(self, event_type: EventType, callback: Any) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
