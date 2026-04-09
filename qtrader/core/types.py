from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from qtrader.core.events import BaseEvent, EventType, FillEvent, OrderEvent, SignalEvent

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal
Signal = SignalEvent
Order = OrderEvent
Fill = FillEvent


class Side:
    BUY = "BUY"
    SELL = "SELL"
    Buy = "BUY"
    Sell = "SELL"
    HOLD = "HOLD"


@dataclass
class MarketData:
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
    symbol: str
    timestamp: datetime
    alpha_values: dict[str, Decimal]
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class ValidatedFeatures:
    symbol: str
    timestamp: datetime
    features: dict[str, Decimal]
    validation_metadata: dict[str, Any]
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class AllocationWeights:
    timestamp: datetime
    weights: dict[str, Decimal]
    trace_id: str
    metadata: dict[str, Any] | None = None


@dataclass
class RiskMetrics:
    timestamp: datetime
    portfolio_var: Decimal
    portfolio_volatility: Decimal
    max_drawdown: Decimal
    leverage: Decimal
    trace_id: str
    metadata: dict[str, Any] | None = None


class LoggerProtocol(Protocol):
    def info(self, message: str, **kwargs: Any) -> None: ...

    def warning(self, message: str, **kwargs: Any) -> None: ...

    def error(self, message: str, **kwargs: Any) -> None: ...

    def debug(self, message: str, **kwargs: Any) -> None: ...

    def critical(self, message: str, **kwargs: Any) -> None: ...
        pass


class ConfigProtocol(Protocol):
    def __getattr__(self, name: str) -> Any: ...

    def __setattr__(self, name: str, value: Any) -> None: ...
        pass


@dataclass
class IngestionTrace:
    price: float
    volatility: float
    spread_bps: float
    is_live: bool
    timestamp: str


@dataclass
class AlphaTrace:
    model_name: str
    action: str
    confidence: float
    indicators: dict[str, float]
    forecast: list[float] | None = None
    reasoning: str | None = None


@dataclass
class RiskTrace:
    initial_stop_loss: float
    initial_take_profit: float
    adjusted_stop_loss: float
    adjusted_take_profit: float
    position_size_pct: float
    notional_usd: float
    risk_score: float


@dataclass
class ExecutionTrace:
    order_id: str
    fill_price: float
    slippage_bps: float
    fee_usd: float
    status: str


@dataclass
class PipelineTrace:
    trace_id: str
    timestamp: str
    ingestion: IngestionTrace | None = None
    alpha: AlphaTrace | None = None
    risk: RiskTrace | None = None
    execution: ExecutionTrace | None = None
    module_traces: dict[str, Any] | None = None


class EventBusProtocol(Protocol):
    async def publish(self, event: BaseEvent) -> bool: ...

    def subscribe(self, event_type: EventType, callback: Any) -> None: ...

    def unsubscribe(self, event_type: EventType, callback: Any) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...
        pass
