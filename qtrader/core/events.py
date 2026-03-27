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


class PipelineErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    module_name: str
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionTracePayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_id: str
    features: dict[str, float]
    signal: float
    decision_price: float
    decision: str
    config_version: int


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
    decision_price: float
    executed_price: float
    quantity: float
    shortfall: float
    total_cost: float
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
    total_slippage: float
    market_impact: float
    timing_cost: float
    fees: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class TCAWarningPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkComparisonPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    trace_id: UUID
    exec_price: float
    vwap: float
    twap: float
    arrival_price: float
    perf_vwap: float
    perf_twap: float
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
    total_cost: float
    impact_pct: float
    timing_pct: float
    fee_pct: float
    funding_pct: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttributionErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_type: str
    details: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueRankingPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    venue: str
    score: float
    rank: int
    metrics: dict[str, float]
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
    avg_shortfall: float
    avg_slippage: float
    vwap_diff: float
    cost_breakdown: dict[str, float]
    best_venue: str
    total_cost: float
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
    pnl: float
    drawdown: float
    sharpe: float
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
    pnl_diff: float
    slippage_diff: float
    price_diff: float
    fidelity_score: float
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
    total_cost: float
    impact_cost: float
    timing_cost: float
    fee_cost: float
    risk_cost: float
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


class PipelineErrorEvent(BaseEvent):
    """Event representing a critical pipeline failure."""
    event_type: EventType = EventType.PIPELINE_ERROR
    payload: PipelineErrorPayload


class DecisionTraceEvent(BaseEvent):
    """Event representing a strategy decision audit trail."""
    event_type: EventType = EventType.DECISION_TRACE
    payload: DecisionTracePayload


class DecisionErrorEvent(BaseEvent):
    """Event representing a strategy decision failure."""
    event_type: EventType = EventType.DECISION_ERROR
    payload: DecisionErrorPayload


class AuditWarningEvent(BaseEvent):
    """Event representing a failure in trade lifecycle reconstruction."""
    event_type: EventType = EventType.AUDIT_WARNING
    payload: AuditWarningPayload


class ReplayAuditErrorEvent(BaseEvent):
    """Event representing a failure in deterministic decision replay."""
    event_type: EventType = EventType.REPLAY_FAILURE
    payload: ReplayAuditErrorPayload


class ComplianceExportEvent(BaseEvent):
    """Event representing a successful compliance data export."""
    event_type: EventType = EventType.COMPLIANCE_EXPORT
    payload: ComplianceExportPayload


class ComplianceErrorEvent(BaseEvent):
    """Event representing a failure in regulatory reporting or export."""
    event_type: EventType = EventType.COMPLIANCE_ERROR
    payload: ComplianceErrorPayload


class ImplementationShortfallEvent(BaseEvent):
    """Event representing the implementation shortfall (TCA) of a trade."""
    event_type: EventType = EventType.IMPLEMENTATION_SHORTFALL
    payload: ImplementationShortfallPayload


class TCAErrorEvent(BaseEvent):
    """Event representing a failure in Transaction Cost Analysis."""
    event_type: EventType = EventType.TCA_ERROR
    payload: TCAErrorPayload


class SlippageBreakdownEvent(BaseEvent):
    """Event representing the decomposition of execution slippage."""
    event_type: EventType = EventType.SLIPPAGE_BREAKDOWN
    payload: SlippageBreakdownPayload


class TCAWarningEvent(BaseEvent):
    """Event representing a non-critical inconsistency during TCA analysis."""
    event_type: EventType = EventType.TCA_WARNING
    payload: TCAWarningPayload


class BenchmarkComparisonEvent(BaseEvent):
    """Event representing the comparison of execution against market benchmarks."""
    event_type: EventType = EventType.BENCHMARK_COMPARISON
    payload: BenchmarkComparisonPayload


class BenchmarkErrorEvent(BaseEvent):
    """Event representing a failure in execution benchmarking."""
    event_type: EventType = EventType.BENCHMARK_ERROR
    payload: BenchmarkErrorPayload


class CostAttributionEvent(BaseEvent):
    """Event representing the granular attribution of trading costs."""
    event_type: EventType = EventType.COST_ATTRIBUTION
    payload: CostAttributionPayload


class AttributionErrorEvent(BaseEvent):
    """Event representing a failure in cost attribution analysis."""
    event_type: EventType = EventType.ATTRIBUTION_ERROR
    payload: AttributionErrorPayload


class VenueRankingEvent(BaseEvent):
    """Event representing the comparative ranking of execution venues."""
    event_type: EventType = EventType.VENUE_RANKING
    payload: VenueRankingPayload


class VenueErrorEvent(BaseEvent):
    """Event representing a failure in venue-specific execution analysis."""
    event_type: EventType = EventType.VENUE_ERROR
    payload: VenueErrorPayload


class TCAReportEvent(BaseEvent):
    """Event representing the global aggregation of TCA metrics."""
    event_type: EventType = EventType.TCA_REPORT
    payload: TCAReportPayload


class TCAReportErrorEvent(BaseEvent):
    """Event representing a failure in global TCA report generation."""
    event_type: EventType = EventType.TCA_REPORT_ERROR
    payload: TCAReportErrorPayload


class StrategyStateEvent(BaseEvent):
    """Event representing a transition in strategy lifecycle state."""
    event_type: EventType = EventType.STRATEGY_STATE
    payload: StrategyStatePayload


class FSMErrorEvent(BaseEvent):
    """Event representing a failed finite state machine transition."""
    event_type: EventType = EventType.FSM_ERROR
    payload: FSMErrorPayload


class SandboxReportEvent(BaseEvent):
    """Event representing the performance report of a sandbox simulation."""
    event_type: EventType = EventType.SANDBOX_REPORT
    payload: SandboxReportPayload


class SandboxErrorEvent(BaseEvent):
    """Event representing a failure or crash in the sandbox environment."""
    event_type: EventType = EventType.SANDBOX_ERROR
    payload: SandboxErrorPayload


class ModelRiskScoreEvent(BaseEvent):
    """Event representing the quantitative risk score of a trading model."""
    event_type: EventType = EventType.MODEL_RISK_SCORE
    payload: ModelRiskScorePayload


class RiskScoreErrorEvent(BaseEvent):
    """Event representing a failure in the model risk scoring pipeline."""
    event_type: EventType = EventType.RISK_SCORE_ERROR
    payload: RiskScoreErrorPayload


class StrategyApprovalEvent(BaseEvent):
    """Event representing the formal approval or rejection of a trading strategy."""
    event_type: EventType = EventType.STRATEGY_APPROVAL
    payload: StrategyApprovalPayload


class ApprovalErrorEvent(BaseEvent):
    """Event representing a failure in the strategy approval pipeline."""
    event_type: EventType = EventType.APPROVAL_ERROR
    payload: ApprovalErrorPayload


class StrategyKillEvent(BaseEvent):
    """Event representing an emergency shutdown of a trading strategy."""
    event_type: EventType = EventType.STRATEGY_KILL
    payload: StrategyKillPayload


class KillErrorEvent(BaseEvent):
    """Event representing a failure in the kill switch system."""
    event_type: EventType = EventType.KILL_ERROR
    payload: KillErrorPayload


class StressTestResultEvent(BaseEvent):
    """Event representing the result of a system stress test."""
    event_type: EventType = EventType.STRESS_TEST_RESULT
    payload: StressTestResultPayload


class StressTestErrorEvent(BaseEvent):
    """Event representing a failure or crash in the stress testing pipeline."""
    event_type: EventType = EventType.STRESS_TEST_ERROR
    payload: StressTestErrorPayload


class FidelityReportEvent(BaseEvent):
    """Event representing the result of a backtest vs live fidelity validation."""
    event_type: EventType = EventType.FIDELITY_REPORT
    payload: FidelityReportPayload


class FidelityErrorEvent(BaseEvent):
    """Event representing a failure in the fidelity calculation pipeline."""
    event_type: EventType = EventType.FIDELITY_ERROR
    payload: FidelityErrorPayload


class SimulationAccuracyEvent(BaseEvent):
    """Event representing the statistical accuracy of a market simulation."""
    event_type: EventType = EventType.SIMULATION_ACCURACY_REPORT
    payload: SimulationAccuracyPayload


class SimulationAccuracyErrorEvent(BaseEvent):
    """Event representing a failure in the simulation accuracy validation pipeline."""
    event_type: EventType = EventType.SIMULATION_ACCURACY_ERROR
    payload: SimulationAccuracyErrorPayload


class CoverageReportEvent(BaseEvent):
    """Event representing the test coverage status of a system component."""
    event_type: EventType = EventType.COVERAGE_REPORT
    payload: CoverageReportPayload


class CoverageErrorEvent(BaseEvent):
    """Event representing a failure in the coverage enforcement pipeline."""
    event_type: EventType = EventType.COVERAGE_ERROR
    payload: CoverageErrorPayload


class ExecutionObjectiveEvent(BaseEvent):
    """Event representing the mathematical cost breakdown of an execution decision."""
    event_type: EventType = EventType.EXECUTION_OBJECTIVE
    payload: ExecutionObjectivePayload


class ExecutionStateEvent(BaseEvent):
    """Event representing the 7-dimensional microstructure state vector (S_t)."""
    event_type: EventType = EventType.EXECUTION_STATE_UPDATE
    payload: ExecutionStatePayload


class ExecutionCostEvent(BaseEvent):
    """Event representing the 4-dimensional microstructure cost decomposition."""
    event_type: EventType = EventType.EXECUTION_COST_REPORT
    payload: ExecutionCostPayload


class MetaDecisionEvent(BaseEvent):
    """Event representing a deterministic meta-control decision (Gov/Life/Constraint)."""
    event_type: EventType = EventType.META_DECISION
    payload: MetaDecisionPayload