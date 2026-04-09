from __future__ import annotations

import time
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    MARKET_DELTA = "MARKET_DELTA"
    GAP_DETECTED = "GAP_DETECTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    GAP_FREE_MARKET = "GAP_FREE_MARKET"
    FEATURE = "FEATURE"
    FEATURES = "FEATURES"
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
    DRIFT_ALERT = "DRIFT_ALERT"
    MODEL_RETRAIN = "MODEL_RETRAIN"
    ERROR = "ERROR"
    HEARTBEAT = "HEARTBEAT"
    SIGNALS = "SIGNAL"
    ORDERS = "ORDER"
    VALIDATED_FEATURES = "VALIDATED_FEATURES"
    RISK_ALERT = "RISK_ALERT"
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
    SYSTEM_BOOT_COMPLETED = "SYSTEM_BOOT_COMPLETED"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    DECISION_TRACE = "DECISION_TRACE"
    DECISION_ERROR = "DECISION_ERROR"
    AUDIT_WARNING = "AUDIT_WARNING"
    REPLAY_FAILURE = "REPLAY_FAILURE"
    COMPLIANCE_EXPORT = "COMPLIANCE_EXPORT"
    COMPLIANCE_ERROR = "COMPLIANCE_ERROR"
    IMPLEMENTATION_SHORTFALL = "IMPLEMENTATION_SHORTFALL"
    TCA_ERROR = "TCA_ERROR"
    SLIPPAGE_BREAKDOWN = "SLIPPAGE_BREAKDOWN"
    TCA_WARNING = "TCA_WARNING"
    BENCHMARK_COMPARISON = "BENCHMARK_COMPARISON"
    BENCHMARK_ERROR = "BENCHMARK_ERROR"
    COST_ATTRIBUTION = "COST_ATTRIBUTION"
    ATTRIBUTION_ERROR = "ATTRIBUTION_ERROR"
    VENUE_RANKING = "VENUE_RANKING"
    VENUE_ERROR = "VENUE_ERROR"
    TCA_REPORT = "TCA_REPORT"
    TCA_REPORT_ERROR = "TCA_REPORT_ERROR"
    STRATEGY_STATE = "STRATEGY_STATE"
    FSM_ERROR = "FSM_ERROR"
    SANDBOX_REPORT = "SANDBOX_REPORT"
    SANDBOX_ERROR = "SANDBOX_ERROR"
    MODEL_RISK_SCORE = "MODEL_RISK_SCORE"
    RISK_SCORE_ERROR = "RISK_SCORE_ERROR"
    STRATEGY_APPROVAL = "STRATEGY_APPROVAL"
    APPROVAL_ERROR = "APPROVAL_ERROR"
    STRATEGY_KILL = "STRATEGY_KILL"
    KILL_ERROR = "KILL_ERROR"
    STRESS_TEST_RESULT = "STRESS_TEST_RESULT"
    STRESS_TEST_ERROR = "STRESS_TEST_ERROR"
    FIDELITY_REPORT = "FIDELITY_REPORT"
    FIDELITY_ERROR = "FIDELITY_ERROR"
    SIMULATION_ACCURACY_REPORT = "SIMULATION_ACCURACY_REPORT"
    SIMULATION_ACCURACY_ERROR = "SIMULATION_ACCURACY_ERROR"
    COVERAGE_REPORT = "COVERAGE_REPORT"
    COVERAGE_ERROR = "COVERAGE_ERROR"
    EXECUTION_OBJECTIVE = "EXECUTION_OBJECTIVE"
    EXECUTION_STATE_UPDATE = "EXECUTION_STATE_UPDATE"
    EXECUTION_COST_REPORT = "EXECUTION_COST_REPORT"
    META_DECISION = "META_DECISION"
    FORENSIC_NOTE = "FORENSIC_NOTE"


class MarketPayload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    seq_id: int | None = None
    data: Any = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    symbol: str
    action: str
    quantity: Decimal
    price: Decimal | None = None
    order_type: str = "MARKET"
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str | None = None
    risk_type: str
    value: Decimal
    threshold: Decimal
    metrics: dict[str, Decimal] = Field(default_factory=dict)
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
    strength: Decimal
    confidence: Decimal = Decimal("0.5")
    metadata: dict[str, Any] = Field(default_factory=dict)


class FillPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    commission: Decimal = Decimal("0.0")
    session_id: str | None = None
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
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]


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
    nav: Decimal
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerEntryPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_id: str
    debit: Decimal
    credit: Decimal
    currency: str = "USD"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    symbol: str
    fee_amount: Decimal
    currency: str = "USD"
    fee_type: str = "TAKER"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FundingPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    position_size: Decimal
    funding_rate: Decimal
    funding_amount: Decimal
    mark_price: Decimal
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


class PipelineErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    module_name: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionTracePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_id: str
    features: dict[str, Any]
    signal: Decimal
    decision_price: Decimal
    decision: str
    config_version: int
    module_traces: dict[str, Any] = Field(default_factory=dict)


class DecisionErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    module_name: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditWarningPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    reason: str
    missing_event_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayAuditErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceExportPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    report_type: str
    file_path: str
    trace_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImplementationShortfallPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    decision_price: Decimal
    executed_price: Decimal
    quantity: Decimal
    shortfall: Decimal
    total_cost: Decimal
    side: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TCAErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SlippageBreakdownPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    total_slippage: Decimal
    market_impact: Decimal
    timing_cost: Decimal
    fees: Decimal
    metadata: dict[str, Any] = Field(default_factory=dict)


class TCAWarningPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkComparisonPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    exec_price: Decimal
    vwap: Decimal
    twap: Decimal
    arrival_price: Decimal
    perf_vwap: Decimal
    perf_twap: Decimal
    side: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostAttributionPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    total_cost: Decimal
    impact_pct: Decimal
    timing_pct: Decimal
    fee_pct: Decimal
    funding_pct: Decimal
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttributionErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueRankingPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    venue: str
    score: Decimal
    rank: int
    metrics: dict[str, Decimal]
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    venue: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TCAReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    period_start: int
    period_end: int
    avg_shortfall: Decimal
    avg_slippage: Decimal
    vwap_diff: Decimal
    cost_breakdown: dict[str, Decimal]
    best_venue: str
    total_cost: Decimal
    trade_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class TCAReportErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyStatePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    old_state: str
    new_state: str
    reason: str = "COMMAND_ISSUED"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FSMErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    entity_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    pnl: Decimal
    drawdown: Decimal
    sharpe: Decimal
    status: str
    trade_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRiskScorePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_id: str
    risk_score: float
    volatility: float
    drawdown: float
    stability: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskScoreErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyApprovalPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    approved: bool
    risk_score: float
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyKillPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    reason: str
    metric: str
    threshold: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class KillErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StressTestResultPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    scenario_id: str
    max_drawdown: float
    kill_triggered: bool
    state_transitions: list[str]
    is_passing: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class StressTestErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    scenario_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class FidelityReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    pnl_diff: Decimal
    slippage_diff: Decimal
    price_diff: Decimal
    fidelity_score: Decimal
    trade_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class FidelityErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationAccuracyPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    scenario_id: str
    mean_diff: float
    variance_diff: float
    kurtosis_diff: float
    correlation: float
    kl_divergence: float
    accuracy_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationAccuracyErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    scenario_id: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoverageReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    package_name: str
    coverage_pct: float
    uncovered_lines: list[int] = Field(default_factory=list)
    event_coverage: dict[str, bool] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoverageErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    module_name: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionObjectivePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    symbol: str
    total_cost: Decimal
    impact_cost: Decimal
    timing_cost: Decimal
    fee_cost: Decimal
    risk_cost: Decimal
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionStatePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    venue: str
    state_vector: list[float]
    features: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionCostPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    total_cost: float
    impact_cost: float
    timing_cost: float
    spread_cost: float
    fee_cost: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetaDecisionPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    module: str
    action: str
    entity_id: str
    decision: str
    reason: str
    metrics: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ForensicNotePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str
    note_type: str
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


from qtrader.core.trace_authority import TraceAuthority


class BaseEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID = Field(
        default_factory=uuid4, description="Unique event identifier for idempotency"
    )
    trace_id: UUID = Field(
        default_factory=TraceAuthority.ensure_trace,
        description="Correlation ID propagated across the pipeline",
    )
    event_type: EventType = Field(description="The type of the event")
    version: int = Field(default=1, description="Schema version for backward compatibility")
    timestamp: int = Field(
        default_factory=lambda: int(time.time() * 1000000),
        description="Microseconds since epoch (normalized)",
    )
    source: str = Field(description="Originating module name")
    payload: Any = Field(description="Event-specific data (BaseModel or dict)")
    partition_key: str | None = Field(
        default=None, description="Key used for deterministic routing"
    )
    delivery_attempt: int = Field(
        default=1, description="Number of times this event has been attempted"
    )
    offset: int | None = Field(
        default=None, description="Monotonically increasing sequence ID per partition"
    )
    is_remote: bool = Field(
        default=False, description="Flag for distributed event bus to prevent loops"
    )

    @property
    def type(self) -> EventType:
        return self.event_type


class EventBusProtocol(Protocol):
    async def publish(self, event: BaseEvent) -> bool: ...

    def subscribe(self, event_type: EventType, callback: Any) -> None: ...

    def unsubscribe(self, event_type: EventType, callback: Any) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class MarketEvent(BaseEvent):
    event_type: EventType = EventType.MARKET_DATA
    payload: MarketPayload

    @property
    def symbol(self) -> str:
        return self.payload.symbol

    @property
    def bid(self) -> Decimal:
        return self.payload.bid

    @property
    def ask(self) -> Decimal:
        return self.payload.ask

    @property
    def seq_id(self) -> int | None:
        return self.payload.seq_id


class OrderEvent(BaseEvent):
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
    def quantity(self) -> Decimal:
        return self.payload.quantity

    @property
    def order_type(self) -> str:
        return self.payload.order_type

    @property
    def side(self) -> str:
        return self.payload.action

    @property
    def price(self) -> Decimal | None:
        return self.payload.price


class SignalEvent(BaseEvent):
    event_type: EventType = EventType.SIGNAL
    payload: SignalPayload

    @property
    def symbol(self) -> str:
        return self.payload.symbol

    @property
    def signal_type(self) -> str:
        return self.payload.signal_type

    @property
    def strength(self) -> Decimal:
        return self.payload.strength

    @property
    def signal(self) -> Decimal:
        if self.payload.signal_type == "BUY":
            return self.payload.strength
        if self.payload.signal_type == "SELL":
            return -self.payload.strength
        return Decimal("0.0")


class RiskEvent(BaseEvent):
    event_type: EventType = EventType.RISK
    payload: RiskPayload

    @property
    def symbol(self) -> str | None:
        return self.payload.symbol


class FillEvent(BaseEvent):
    event_type: EventType = EventType.FILL
    payload: FillPayload

    @property
    def order_id(self) -> str:
        return self.payload.order_id

    @property
    def symbol(self) -> str:
        return self.payload.symbol

    @property
    def side(self) -> str:
        return self.payload.side

    @property
    def quantity(self) -> Decimal:
        return self.payload.quantity

    @property
    def price(self) -> Decimal:
        return self.payload.price

    @property
    def commission(self) -> Decimal:
        return self.payload.commission


class SystemEvent(BaseEvent):
    event_type: EventType = EventType.SYSTEM
    payload: SystemPayload


class ErrorEvent(BaseEvent):
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
    def bid(self) -> Decimal:
        return self.payload.bids[0][0] if self.payload.bids else Decimal("0.0")

    @property
    def ask(self) -> Decimal:
        return self.payload.asks[0][0] if self.payload.asks else Decimal("0.0")


class FeatureEvent(BaseEvent):
    event_type: EventType = EventType.FEATURES
    payload: FeaturePayload


class ValidatedFeatureEvent(BaseEvent):
    event_type: EventType = EventType.VALIDATED_FEATURES
    payload: FeaturePayload


class ClockSyncEvent(BaseEvent):
    event_type: EventType = EventType.CLOCK_SYNC
    payload: ClockSyncPayload


class NAVEvent(BaseEvent):
    event_type: EventType = EventType.NAV_UPDATED
    payload: NAVPayload


class LedgerEntryEvent(BaseEvent):
    event_type: EventType = EventType.LEDGER_ENTRY
    payload: LedgerEntryPayload


class FeeEvent(BaseEvent):
    event_type: EventType = EventType.FEE_CALCULATED
    payload: FeePayload


class FundingEvent(BaseEvent):
    event_type: EventType = EventType.FUNDING_CALCULATED
    payload: FundingPayload


class ConfigChangeEvent(BaseEvent):
    event_type: EventType = EventType.CONFIG_CHANGED
    payload: ConfigChangePayload


class RiskApprovedEvent(BaseEvent):
    event_type: EventType = EventType.RISK_APPROVED
    payload: RiskApprovedPayload


class RiskRejectedEvent(BaseEvent):
    event_type: EventType = EventType.RISK_REJECTED
    payload: RiskRejectedPayload


class PipelineErrorEvent(BaseEvent):
    event_type: EventType = EventType.PIPELINE_ERROR
    payload: PipelineErrorPayload


class DecisionTraceEvent(BaseEvent):
    event_type: EventType = EventType.DECISION_TRACE
    payload: DecisionTracePayload


class DecisionErrorEvent(BaseEvent):
    event_type: EventType = EventType.DECISION_ERROR
    payload: DecisionErrorPayload


class AuditWarningEvent(BaseEvent):
    event_type: EventType = EventType.AUDIT_WARNING
    payload: AuditWarningPayload


class ReplayAuditErrorEvent(BaseEvent):
    event_type: EventType = EventType.REPLAY_FAILURE
    payload: ReplayAuditErrorPayload


class ComplianceExportEvent(BaseEvent):
    event_type: EventType = EventType.COMPLIANCE_EXPORT
    payload: ComplianceExportPayload


class ComplianceErrorEvent(BaseEvent):
    event_type: EventType = EventType.COMPLIANCE_ERROR
    payload: ComplianceErrorPayload


class ImplementationShortfallEvent(BaseEvent):
    event_type: EventType = EventType.IMPLEMENTATION_SHORTFALL
    payload: ImplementationShortfallPayload


class TCAErrorEvent(BaseEvent):
    event_type: EventType = EventType.TCA_ERROR
    payload: TCAErrorPayload


class SlippageBreakdownEvent(BaseEvent):
    event_type: EventType = EventType.SLIPPAGE_BREAKDOWN
    payload: SlippageBreakdownPayload


class TCAWarningEvent(BaseEvent):
    event_type: EventType = EventType.TCA_WARNING
    payload: TCAWarningPayload


class BenchmarkComparisonEvent(BaseEvent):
    event_type: EventType = EventType.BENCHMARK_COMPARISON
    payload: BenchmarkComparisonPayload


class BenchmarkErrorEvent(BaseEvent):
    event_type: EventType = EventType.BENCHMARK_ERROR
    payload: BenchmarkErrorPayload


class CostAttributionEvent(BaseEvent):
    event_type: EventType = EventType.COST_ATTRIBUTION
    payload: CostAttributionPayload


class AttributionErrorEvent(BaseEvent):
    event_type: EventType = EventType.ATTRIBUTION_ERROR
    payload: AttributionErrorPayload


class VenueRankingEvent(BaseEvent):
    event_type: EventType = EventType.VENUE_RANKING
    payload: VenueRankingPayload


class VenueErrorEvent(BaseEvent):
    event_type: EventType = EventType.VENUE_ERROR
    payload: VenueErrorPayload


class TCAReportEvent(BaseEvent):
    event_type: EventType = EventType.TCA_REPORT
    payload: TCAReportPayload


class TCAReportErrorEvent(BaseEvent):
    event_type: EventType = EventType.TCA_REPORT_ERROR
    payload: TCAReportErrorPayload


class StrategyStateEvent(BaseEvent):
    event_type: EventType = EventType.STRATEGY_STATE
    payload: StrategyStatePayload


class FSMErrorEvent(BaseEvent):
    event_type: EventType = EventType.FSM_ERROR
    payload: FSMErrorPayload


class SandboxReportEvent(BaseEvent):
    event_type: EventType = EventType.SANDBOX_REPORT
    payload: SandboxReportPayload


class SandboxErrorEvent(BaseEvent):
    event_type: EventType = EventType.SANDBOX_ERROR
    payload: SandboxErrorPayload


class ModelRiskScoreEvent(BaseEvent):
    event_type: EventType = EventType.MODEL_RISK_SCORE
    payload: ModelRiskScorePayload


class RiskScoreErrorEvent(BaseEvent):
    event_type: EventType = EventType.RISK_SCORE_ERROR
    payload: RiskScoreErrorPayload


class StrategyApprovalEvent(BaseEvent):
    event_type: EventType = EventType.STRATEGY_APPROVAL
    payload: StrategyApprovalPayload


class ApprovalErrorEvent(BaseEvent):
    event_type: EventType = EventType.APPROVAL_ERROR
    payload: ApprovalErrorPayload


class StrategyKillEvent(BaseEvent):
    event_type: EventType = EventType.STRATEGY_KILL
    payload: StrategyKillPayload


class KillErrorEvent(BaseEvent):
    event_type: EventType = EventType.KILL_ERROR
    payload: KillErrorPayload


class StressTestResultEvent(BaseEvent):
    event_type: EventType = EventType.STRESS_TEST_RESULT
    payload: StressTestResultPayload


class StressTestErrorEvent(BaseEvent):
    event_type: EventType = EventType.STRESS_TEST_ERROR
    payload: StressTestErrorPayload


class FidelityReportEvent(BaseEvent):
    event_type: EventType = EventType.FIDELITY_REPORT
    payload: FidelityReportPayload


class FidelityErrorEvent(BaseEvent):
    event_type: EventType = EventType.FIDELITY_ERROR
    payload: FidelityErrorPayload


class SimulationAccuracyEvent(BaseEvent):
    event_type: EventType = EventType.SIMULATION_ACCURACY_REPORT
    payload: SimulationAccuracyPayload


class SimulationAccuracyErrorEvent(BaseEvent):
    event_type: EventType = EventType.SIMULATION_ACCURACY_ERROR
    payload: SimulationAccuracyErrorPayload


class CoverageReportEvent(BaseEvent):
    event_type: EventType = EventType.COVERAGE_REPORT
    payload: CoverageReportPayload


class CoverageErrorEvent(BaseEvent):
    event_type: EventType = EventType.COVERAGE_ERROR
    payload: CoverageErrorPayload


class ExecutionObjectiveEvent(BaseEvent):
    event_type: EventType = EventType.EXECUTION_OBJECTIVE
    payload: ExecutionObjectivePayload


class ExecutionStateEvent(BaseEvent):
    event_type: EventType = EventType.EXECUTION_STATE_UPDATE
    payload: ExecutionStatePayload


class ExecutionCostEvent(BaseEvent):
    event_type: EventType = EventType.EXECUTION_COST_REPORT
    payload: ExecutionCostPayload


class MetaDecisionEvent(BaseEvent):
    event_type: EventType = EventType.META_DECISION
    payload: MetaDecisionPayload


class ForensicNoteEvent(BaseEvent):
    event_type: EventType = EventType.FORENSIC_NOTE
    payload: ForensicNotePayload


EVENT_TYPE_MAP: dict[EventType, type[BaseEvent]] = {
    EventType.MARKET_DATA: MarketEvent,
    EventType.ORDER: OrderEvent,
    EventType.SIGNAL: SignalEvent,
    EventType.RISK: RiskEvent,
    EventType.FILL: FillEvent,
    EventType.SYSTEM: SystemEvent,
    EventType.ERROR: ErrorEvent,
    EventType.FORENSIC_NOTE: ForensicNoteEvent,
}
