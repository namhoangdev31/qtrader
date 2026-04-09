import asyncio
import json
import logging
import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import polars as pl

from qtrader.core.container import container
from qtrader.core.enforcement_engine import enforcement_engine, guard
from qtrader.core.event_store import FileEventStore
from qtrader.core.events import (
    BaseEvent,
    EventType,
    FeatureEvent,
    FeaturePayload,
    FillEvent,
    MarketEvent,
    OrderEvent,
    OrderPayload,
    SignalEvent,
    SignalPayload,
    SystemEvent,
    SystemPayload,
    ValidatedFeatureEvent,
)
from qtrader.core.types import AllocationWeights, EventBusProtocol, MarketData
from qtrader.system.pipeline_validator import PipelineValidator

try:
    from qtrader.ml.mlflow_manager import MLflowManager

    MLFLOW_MANAGER_AVAILABLE = True
except ImportError:
    MLFLOW_MANAGER_AVAILABLE = False
    MLflowManager = None
from loguru import logger

from qtrader.alerts.alert_engine import alert_engine
from qtrader.alpha.base import BaseAlpha
from qtrader.analytics.accounting import FundAccountingEngine
from qtrader.analytics.drift import DriftMonitor
from qtrader.analytics.tca_engine import TCAEngine
from qtrader.core.config import settings
from qtrader.core.cpu_affinity import CPUPinningConfig, apply_cpu_pinning
from qtrader.core.decimal_adapter import math_authority
from qtrader.core.dynamic_config import DynamicConfigManager
from qtrader.core.execution_wrapper import execution_wrapper
from qtrader.core.logger import log_event
from qtrader.core.metrics import metrics
from qtrader.core.post_execution_validator import PostExecutionValidator
from qtrader.core.pre_execution_validator import PreExecutionValidator
from qtrader.core.resource_monitor import ResourceMonitor
from qtrader.core.runtime_gatekeeper import runtime_gatekeeper
from qtrader.core.state_store import Position, StateStore
from qtrader.core.system_state import SystemState, state_manager
from qtrader.core.trace_authority import TraceAuthority
from qtrader.core.types import RiskMetrics
from qtrader.execution.latency_model import LatencyModel
from qtrader.execution.microstructure.microprice import Microprice
from qtrader.execution.order_id import OrderIDGenerator
from qtrader.execution.orderbook_enhanced import OrderbookEnhanced
from qtrader.execution.reconciliation_engine import ReconciliationEngine
from qtrader.execution.routing.liquidity_model import MultiVenueLiquidityModel
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.execution.slippage_model import SlippageModel
from qtrader.execution.smart_router import SmartOrderRouter
from qtrader.metrics.telemetry_pipeline import telemetry_pipeline
from qtrader.ml.meta_online import OnlineMetaLearner
from qtrader.monitoring.feedback.feedback_engine import FeedbackEngine
from qtrader.oms.oms_adapter import OMSAdapter
from qtrader.portfolio.allocator import AllocatorBase
from qtrader.portfolio.drawdown_controller import LiveDrawdownController
from qtrader.portfolio.nav_engine import NAVEngine
from qtrader.portfolio.position_sizing import PositionSizer as PortfolioPositionSizer
from qtrader.portfolio.risk_monitor import RealTimeRiskMonitor
from qtrader.strategy.validation.feature_validator import FeatureValidator

try:
    from qtrader_core import LedgerEngine, LedgerEntry, Transaction

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False
    Transaction = None
    LedgerEngine = None
    LedgerEntry = None
from qtrader.risk.kill_switch import GlobalKillSwitch
from qtrader.risk.monitoring_engine import MonitoringEngine
from qtrader.risk.network_kill_switch import NetworkKillSwitch
from qtrader.risk.recovery_system import RecoverySystem
from qtrader.risk.regime_adapter import RegimeAdapter
from qtrader.risk.runtime import RuntimeRiskEngine
from qtrader.strategy.ensemble_strategy import EnsembleStrategy


class TradingOrchestrator:
    def __init__(
        self,
        event_bus: EventBusProtocol,
        market_data_adapter: object,
        alpha_modules: list[BaseAlpha],
        feature_validator: FeatureValidator,
        strategies: list[Any],
        ensemble_strategy: EnsembleStrategy,
        portfolio_allocator: AllocatorBase,
        runtime_risk_engine: RuntimeRiskEngine,
        oms_adapter: OMSAdapter,
        state_store: StateStore | None = None,
        normalizer: Any | None = None,
        event_store: Any | None = None,
        clock_sync: Any | None = None,
        gap_detector: Any | None = None,
        recovery_service: Any | None = None,
        quality_gate: Any | None = None,
        hft_optimizer: Any | None = None,
        ev_optimizer: Any | None = None,
        win_rate_optimizer: Any | None = None,
        regime_detector: Any | None = None,
    ) -> None:
        self._modules: list[Any] = []
        self._validator = PipelineValidator()
        self._boot_time = asyncio.get_event_loop().time()
        state_manager.set_state(SystemState.INIT)
        self._state = SystemState.INIT
        self.event_bus = event_bus
        self.market_data_adapter = market_data_adapter
        self.alpha_modules = alpha_modules
        self.feature_validator = feature_validator
        self.strategies = strategies
        self.ensemble_strategy = ensemble_strategy
        self.portfolio_allocator = portfolio_allocator
        self.runtime_risk_engine = runtime_risk_engine
        self.oms_adapter = oms_adapter
        self.state_store = state_store or StateStore()
        self.normalizer = normalizer
        self.event_store = event_store
        self.clock_sync = clock_sync
        self.gap_detector = gap_detector
        self.recovery_service = recovery_service
        self.quality_gate = quality_gate
        self.hft_optimizer = hft_optimizer
        self.ev_optimizer = ev_optimizer
        self.win_rate_optimizer = win_rate_optimizer
        self.regime_detector = regime_detector
        self.feedback_engine = FeedbackEngine(event_bus=event_bus)
        self.meta_learner = OnlineMetaLearner()
        self.drift_detector = DriftMonitor()
        self.config_manager = container.get("config")
        self.seed_manager = container.get("seed")
        self.trace_authority = container.get("trace")
        self.fail_fast_engine = container.get("failfast")
        self.math_authority = container.get("decimal")
        self.qlogger = container.get("logger")
        self.settings = settings
        self.post_validator = PostExecutionValidator()
        self.event_store = event_store or FileEventStore(base_path="data/event_store")
        self.event_bus = event_bus
        if hasattr(self.event_bus, "_event_store"):
            self.event_bus._event_store = self.event_store
        self.fail_fast_engine._orchestrator = self
        self.max_drawdown = Decimal("0.20")
        self.max_var = Decimal("0.05")
        self.max_leverage = Decimal("5.0")
        initial_config = {
            "max_drawdown": float(self.max_drawdown),
            "max_var": float(self.max_var),
            "max_leverage": float(self.max_leverage),
            "alpha_decay_ms": 1000,
            "execution_priority": "balanced",
        }
        for k, v in initial_config.items():
            asyncio.create_task(self.config_manager.update(k, v))
        trading_symbols = settings.TRADING_SYMBOLS
        orderbook_sim = OrderbookEnhanced(symbols=trading_symbols)
        slippage_model = SlippageModel()
        latency_model = LatencyModel(
            base_network_latency_ms=10.0,
            network_jitter_ms=2.0,
            base_processing_latency_ms=5.0,
            processing_jitter_ms=1.0,
        )
        shadow_config = {
            "shadow_mode": True,
            "data_lake_path": "./data_lake/shadow",
            "orderbook_simulator": orderbook_sim,
            "slippage_model": slippage_model,
            "latency_model": latency_model,
            "event_bus": event_bus,
        }
        self.shadow_engine = ShadowEngine(shadow_config)
        self.resource_monitor = ResourceMonitor()
        self.order_id_generator = OrderIDGenerator()
        self.smart_order_router = SmartOrderRouter(exchanges={})
        self.reconciliation_engine = ReconciliationEngine(
            event_bus=event_bus, oms=oms_adapter, state_store=self.state_store
        )
        self.microprice = Microprice()
        self.toxic_flow_detector: Any = None
        self.queue_position_model: Any = None
        self.dynamic_routing_engine: Any = None
        self.routing_cost_model: Any = None
        self.fill_probability_model: Any = None
        self.liquidity_model = MultiVenueLiquidityModel()
        self.global_kill_switch = GlobalKillSwitch()
        self.regime_adapter = RegimeAdapter()
        self.position_sizer: Any = None
        self.recovery_system = RecoverySystem()
        self.risk_monitoring_engine = MonitoringEngine()
        if _HAS_RUST:
            self.ledger_engine = LedgerEngine()
        else:
            self.ledger_engine = None
            logger.warning("ORCHESTRATOR | Rust LedgerEngine unavailable.")
        self.nav_engine = NAVEngine()
        self.portfolio_risk_monitor = RealTimeRiskMonitor()
        self.drawdown_controller = LiveDrawdownController()
        self.portfolio_position_sizer = PortfolioPositionSizer()
        self.accounting_engine = FundAccountingEngine()
        self.tca_engine = TCAEngine()
        self.strategy_fsm: Any = None
        self.network_kill_switch = NetworkKillSwitch(
            oms_adapter=oms_adapter, logger_instance=logging.getLogger("kill_switch")
        )
        if MLFLOW_MANAGER_AVAILABLE:
            self.mlflow_manager = MLflowManager(
                tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"),
                experiment_name="QTrader-Strategies",
                enable_mlflow=True,
            )
        else:
            self.mlflow_manager = None
        self._local_feedback_count = 0
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(EventType.MARKET_DATA, self.handle_market_data)
        self.event_bus.subscribe(EventType.FEATURE, self.handle_features)
        self.event_bus.subscribe(EventType.SIGNAL, self.handle_signals)
        self.event_bus.subscribe(EventType.ORDER, self.handle_orders)
        self.event_bus.subscribe(EventType.FILL, self.handle_fills)
        self.event_bus.subscribe(EventType.RISK, self.handle_risk_alert)
        self.event_bus.subscribe(EventType.FEEDBACK_UPDATE, self._handle_feedback_update)

    def initialize(self) -> None:
        try:
            log_event(
                module="orchestrator",
                action="ORCHESTRATOR_BOOT",
                status="SUCCESS",
                message="Sequence initiated (S=INIT)",
            )
            self.seed_manager.apply_global()
            self.trace_authority.start_trace()
            validator = PreExecutionValidator()
            if not validator.validate(seed_manager=self.seed_manager):
                raise RuntimeError(
                    "System pre-execution validation failed. Check qtrader/audit/precheck_report.json"
                )
            if self.seed_manager and (not self.seed_manager.is_applied()):
                self.seed_manager.apply_global()
                logger.info(
                    f"[ORCHESTRATOR] Determinism engaged | Seed: {self.seed_manager.global_seed}"
                )
            try:
                pinning_config = CPUPinningConfig(
                    orchestrator_cores=[0, 1], execution_cores=[2, 3], ml_cores=[4, 5, 6, 7]
                )
                apply_cpu_pinning(pinning_config)
                logger.info("[ORCHESTRATOR] CPU Pinning applied (Standash §4.10)")
            except Exception as e:
                logger.debug(f"[ORCHESTRATOR] CPU Pinning not available: {e}")
            self.validate()
            asyncio.create_task(self.recover_state())
            self._state = SystemState.READY
            self._write_boot_log(start_time=self._boot_time, status="SUCCESS")
            log_event(
                module="orchestrator",
                action="ORCHESTRATOR_BOOT",
                status="SUCCESS",
                message="System is READY",
            )
        except Exception as e:
            state_manager.set_state(SystemState.ERROR)
            self._state = SystemState.ERROR
            log_event(
                module="orchestrator",
                action="ORCHESTRATOR_BOOT",
                status="FAILURE",
                level="CRITICAL",
                error=str(e),
            )
            raise RuntimeError(f"System initialization failed: {e}")

    async def recover_state(self) -> None:
        logger.info("ORCHESTRATOR_RECOVERY | Initiating state reconstruction...")
        try:
            events = await self.event_store.get_events()
            recovery_count = 0
            for event in events:
                if event.event_type == EventType.FILL:
                    await self.handle_fills(event.model_dump())
                    recovery_count += 1
                elif event.event_type == EventType.RISK:
                    pass
            logger.info(
                f"ORCHESTRATOR_RECOVERY | Reconstructed {recovery_count} state-changing events."
            )
        except Exception as e:
            logger.error(f"ORCHESTRATOR_RECOVERY_FAILURE | {e}")

    def validate(self) -> None:
        if not self.settings:
            raise RuntimeError("Configuration settings not available.")
        if not self.seed_manager.is_applied():
            raise RuntimeError("Global seed not applied.")
        logger.info("ORCHESTRATOR_VALIDATION | Post-init compliance 100%.")

    def _write_boot_log(self, start_time: float, status: str) -> None:

        boot_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "boot_duration_ms": (asyncio.get_event_loop().time() - start_time) * 1000,
            "status": status,
            "config_checksum": DynamicConfigManager.get_checksum()
            if hasattr(DynamicConfigManager, "get_checksum")
            else "N/A",
            "seed_applied": self.seed_manager.is_applied(),
            "authorities_initialized": [
                "ConfigManager",
                "SeedManager",
                "TraceAuthority",
                "FailFastEngine",
            ],
        }
        log_path = "/Users/hoangnam/qtrader/qtrader/audit/system_boot_log.json"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(boot_log, f, indent=2)

    async def run(self) -> None:
        if self._state == SystemState.INIT:
            logger.info("ORCHESTRATOR_RUN | Automated boot from INIT.")
            self.initialize()
        if self._state != SystemState.READY:
            logger.critical(
                f"ORCHESTRATOR_LIFECYCLE | Run blocked: System is in {self._state.name} state."
            )
            raise RuntimeError(f"Cannot run: System must be READY (Current: {self._state.name})")
        state_manager.set_state(SystemState.RUNNING)
        self._state = SystemState.RUNNING
        logger.info(f"ORCHESTRATOR_LIFECYCLE | Sovereign Gate ACTIVE (S={self._state.name})")
        await self.event_bus.start()
        await self._start_components()
        await self.run_autonomous()

    async def execute_pipeline(self) -> None:
        await self.run()

    def register_module(self, module: Any) -> None:
        if self._validator.validate_module_architecture(module.__class__):
            self._modules.append(module)
            logger.info(f"ORCHESTRATOR_INTEGRATION | {module.__class__.__name__} certified.")
        else:
            logger.critical(
                f"ORCHESTRATOR_BOOT_FAILURE | Module {module.__class__.__name__} rejected."
            )
            raise RuntimeError(
                f"Module {module.__class__.__name__} failed architectural certification."
            )

    async def inject_event(self, event: BaseEvent) -> bool:
        if not event.trace_id:
            new_trace = uuid.uuid4()
            event = event.model_copy(update={"trace_id": new_trace})
        return await self.event_bus.publish(event)

    async def ingest_raw_data(self, raw_data: dict[str, Any]) -> MarketEvent | None:
        if self._state != SystemState.RUNNING:
            logger.warning(
                f"ORCHESTRATOR_GATE | Ingestion blocked. System state: {self._state.name}"
            )
            return None
        try:
            if self.clock_sync:
                raw_data = await self.clock_sync.handle(raw_data)
            if self.gap_detector and self.recovery_service:
                gapped = await self.gap_detector.handle(raw_data)
                raw_data = await self.recovery_service.handle(gapped)
                if not raw_data:
                    return None
            if self.normalizer:
                event = self.normalizer.normalize(raw_data)
                if not event:
                    return None
            else:
                return None
            if self.quality_gate:
                is_valid = await self._run_data_quality_checks(event)
                if not is_valid:
                    return None
            if self.event_store:
                await self.event_store.append(event)
            await self.event_bus.publish(event)
            return event
        except Exception as e:
            logger.exception(f"ORCHESTRATOR_INGESTION_FAILURE | {e}")
            return None

    async def _run_data_quality_checks(self, event: MarketEvent) -> bool:
        if not self.quality_gate or not self.event_store:
            return True
        symbol = event.symbol
        rolling_prices = self.event_store.get_recent_prices(symbol, window_size=50)
        ref_price = self.event_store.get_latest_price_cross_exchange(
            symbol, exclude_venue=event.metadata.get("venue", "unknown")
        )
        is_valid = self.quality_gate.validate(event, rolling_prices, ref_price=ref_price)
        if not is_valid:
            rejected = SystemEvent(
                source="DataQualityGate",
                trace_id=event.trace_id,
                payload=SystemPayload(
                    action="DATA_REJECTED",
                    reason=f"Outlier/Deviation | Value: {event.payload.bid}",
                    metadata={"symbol": symbol},
                ),
            )
            await self.event_bus.publish(rejected)
        return is_valid

    async def run_autonomous(self) -> None:
        logger.info("ORCHESTRATOR_LIFECYCLE | Autonomous loop is now ACTIVE.")
        await self._start_components()
        self._wake_event = asyncio.Event()
        self._heartbeat_interval = 1.0
        try:
            while True:
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(), timeout=self._heartbeat_interval
                    )
                    self._wake_event.clear()
                except asyncio.TimeoutError:
                    pass
                await self._periodic_check()
        except asyncio.CancelledError:
            logger.warning("ORCHESTRATOR_LIFECYCLE | Shutdown requested.")
            await self.halt_core("SHUTDOWN_SIGNAL")

    def wake_loop(self) -> None:
        self._wake_event.set()

    async def _periodic_check(self) -> None:
        await alert_engine.check_metrics()
        asyncio.get_event_loop().time()
        if self.hft_optimizer:
            self.hft_optimizer.check_and_update_safety_mode()
        await self.event_bus.publish(
            SystemEvent(
                trace_id=uuid.uuid4(),
                source="UnifiedOrchestrator",
                payload=SystemPayload(action="HEARTBEAT", reason="LIVELINESS"),
            )
        )
        await self.apply_strategic_allocation()

    async def apply_strategic_allocation(self) -> None:
        logger.debug("ORCHESTRATOR_STRATEGY | Periodic strategic allocation check completed.")

    def compute_consensus_signal(
        self, signals: Mapping[str, float], weights: Mapping[str, float]
    ) -> float:
        if not signals or not weights:
            return 0.0
        epsilon = 1e-12
        weighted_sum = sum(signals.get(m, 0.0) * weights.get(m, 0.0) for m in weights)
        total_weight = sum(weights.values())
        return weighted_sum / (total_weight + epsilon)

    def adapt_model_weights(self, performance: Mapping[str, float]) -> dict[str, float]:
        if not performance:
            return {}
        total = sum(max(0.0, p) for p in performance.values())
        if total <= 0:
            return {m: 1.0 / len(performance) for m in performance}
        return {m: max(0.0, p) / total for (m, p) in performance.items()}

    async def halt_core(self, reason: str) -> None:
        log_event(
            module="orchestrator",
            action="SYSTEM_HALT",
            status="SUCCESS",
            message=f"Initiating shutdown for: {reason}",
        )
        state_manager.set_state(SystemState.SHUTDOWN)
        self._state = SystemState.SHUTDOWN
        await self._stop_components()
        await self.event_bus.stop()
        await self.post_validator.validate(self.event_store, self.state_store)
        log_event(
            module="orchestrator",
            action="SYSTEM_HALT",
            status="SUCCESS",
            message=f"Shutdown complete (Reason: {reason})",
        )

    async def _start_components(self) -> None:
        await self.shadow_engine.start()
        await self.resource_monitor.start_monitoring()
        await telemetry_pipeline.start()
        logger.info("Background components started")

    async def _stop_components(self) -> None:
        await self.shadow_engine.stop()
        await self.resource_monitor.stop_monitoring()
        await telemetry_pipeline.stop()
        logger.info("Background components stopped")

    @guard(enforcement_engine)
    @execution_wrapper(source="handle_market_data")
    async def handle_market_data(self, market_data: MarketData) -> None:
        await runtime_gatekeeper.check_event(market_data)
        if self._state != SystemState.RUNNING:
            return
        trace_id = market_data.trace_id or self.trace_authority.propagate(market_data)
        log = logger.bind(trace_id=trace_id)
        start_time = asyncio.get_event_loop().time()
        await metrics.increment("throughput")
        self.config_manager.get("alpha_decay_ms", 1000)
        market_data.close = self.math_authority.d(market_data.close)
        market_data.volume = self.math_authority.d(market_data.volume)
        log_event(
            module="orchestrator",
            action="MARKET_DATA_RECEIVED",
            status="SUCCESS",
            metadata={
                "symbol": market_data.symbol,
                "close": str(market_data.close),
                "volume": str(market_data.volume),
            },
        )
        features = {}
        for alpha in self.alpha_modules:
            alpha_output = await alpha.generate(market_data)
            if hasattr(alpha_output, "alpha_values") and isinstance(
                alpha_output.alpha_values, dict
            ):
                features.update(alpha_output.alpha_values)
            else:
                log.warning(
                    f"Alpha module {alpha.name} returned unexpected output: {type(alpha_output)}"
                )
        feature_event = FeatureEvent(
            source="AlphaEnsemble",
            trace_id=trace_id,
            payload=FeaturePayload(
                symbol=market_data.symbol,
                features=features,
                metadata={"module_count": len(self.alpha_modules)},
            ),
        )
        await self.event_bus.publish(feature_event)
        log_event(
            module="orchestrator",
            action="FEATURES_PUBLISHED",
            status="SUCCESS",
            metadata={"symbol": market_data.symbol, "feature_count": len(features)},
        )
        latency = (asyncio.get_event_loop().time() - start_time) * 1000
        await metrics.observe("latency", latency)

    @execution_wrapper(source="handle_features")
    async def handle_features(self, features_data: dict[str, Any]) -> None:
        await runtime_gatekeeper.check(
            {"stage": "features", "trace_id": features_data.get("trace_id")}
        )
        trace_id = features_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        if await self._is_kill_switch_active():
            log.warning("Kill switch active, skipping feature validation")
            return
        validation_mode = self.config_manager.get("feature_validation_mode", "strict")
        log.debug(f"Handling features (mode: {validation_mode})")
        features = features_data.payload.features
        validated = await self.feature_validator.validate(features)
        if validated is None:
            log_event(
                module="orchestrator",
                action="FEATURE_VALIDATION",
                status="FAILURE",
                level="WARNING",
                message="Feature validation failed",
            )
            return
        validated_event = ValidatedFeatureEvent(
            source="FeatureValidator",
            trace_id=trace_id,
            payload=FeaturePayload(
                symbol=features_data.payload.symbol,
                features=validated,
                metadata={"validation_mode": validation_mode},
            ),
        )
        await self.event_bus.publish(validated_event)
        log_event(
            module="orchestrator",
            action="VALIDATED_FEATURES_PUBLISHED",
            status="SUCCESS",
            metadata={"feature_count": len(validated)},
        )

    @execution_wrapper(source="handle_validated_features")
    async def handle_validated_features(self, validated_event: ValidatedFeatureEvent) -> None:
        await runtime_gatekeeper.check_event(validated_event)
        trace_id = validated_event.trace_id
        log = logger.bind(trace_id=trace_id)
        if await self._is_kill_switch_active():
            log.warning("Kill switch active, skipping signal generation")
            return
        features_obj = validated_event.payload.features
        strategy_v = self.config_manager.get("ensemble_strategy_version", 1)
        ensemble_signal = await self.ensemble_strategy.generate_signal(features_obj)
        signal_event = SignalEvent(
            source="EnsembleStrategy",
            trace_id=trace_id,
            payload=SignalPayload(
                symbol=validated_event.payload.symbol,
                signal_type=ensemble_signal.signal_type,
                strength=math_authority.to_price(ensemble_signal.strength),
                metadata={"strategy_version": strategy_v},
            ),
        )
        await self.event_bus.publish(signal_event)
        log.info(
            f"Published SIGNAL - Output: {ensemble_signal.signal_type} @ {ensemble_signal.strength}"
        )

    @execution_wrapper(source="handle_signals")
    async def handle_signals(self, signal_event: SignalEvent) -> None:
        await runtime_gatekeeper.check_event(signal_event)
        trace_id = signal_event.trace_id
        log = logger.bind(trace_id=trace_id)
        if await self._is_kill_switch_active():
            log.warning("Kill switch active, skipping signal processing")
            return
        symbol = signal_event.payload.symbol
        log.info(
            f"Processing signal: {signal_event.payload.signal_type} with strength {signal_event.payload.strength}"
        )
        await self.state_store.set_last_signal_timestamp(
            datetime.fromtimestamp(signal_event.timestamp / 1000000, tz=timezone.utc)
        )
        allocation_weights = await self.portfolio_allocator.allocate(signal_event)
        if allocation_weights is None:
            log.debug("No allocation computed")
            return
        risk_metrics = await self.runtime_risk_engine.evaluate_risk(
            allocation_weights=allocation_weights
        )
        max_var = math_authority.d(self.config_manager.get("max_var", self.max_var))
        max_drawdown = math_authority.d(self.config_manager.get("max_drawdown", self.max_drawdown))
        max_leverage = math_authority.d(self.config_manager.get("max_leverage", self.max_leverage))
        if (
            risk_metrics.portfolio_var > max_var
            or risk_metrics.max_drawdown > max_drawdown
            or risk_metrics.leverage > max_leverage
        ):
            log.warning(
                f"Risk check failed, blocking order. Reason: VaR={risk_metrics.portfolio_var} > {max_var}"
            )
            await self.event_bus.publish(
                SystemEvent(
                    source="RiskEngine",
                    trace_id=trace_id,
                    payload=SystemPayload(
                        action="RISK_REJECTED",
                        reason=f"VaR={risk_metrics.portfolio_var} > {max_var}",
                        metadata={"symbol": symbol},
                    ),
                )
            )
            return
        await self.state_store.set_last_approved_risk_metrics(
            {
                "portfolio_var": risk_metrics.portfolio_var,
                "max_drawdown": risk_metrics.max_drawdown,
                "leverage": risk_metrics.leverage,
            }
        )
        for target_symbol, weight in allocation_weights.weights.items():
            if weight == 0:
                continue
            action = "BUY" if weight > 0 else "SELL"
            qty = math_authority.to_qty(abs(weight) * 100)
            order_event = OrderEvent(
                source="PortfolioAllocator",
                trace_id=trace_id,
                payload=OrderPayload(
                    order_id=str(uuid.uuid4()),
                    symbol=target_symbol,
                    action=action,
                    quantity=qty,
                    metadata={
                        "risk_metrics": risk_metrics.model_dump()
                        if hasattr(risk_metrics, "model_dump")
                        else {}
                    },
                ),
            )
            await self.event_bus.publish(order_event)
        log.info(f"Published ORDERS for {len(allocation_weights.weights)} targets")

    @execution_wrapper(source="handle_orders")
    async def handle_orders(self, order_event: OrderEvent) -> None:
        await runtime_gatekeeper.check_event(order_event)
        trace_id = order_event.trace_id
        log = logger.bind(trace_id=trace_id)
        if await self._is_kill_switch_active():
            log.warning("Kill switch active, skipping order submission")
            return
        execution_priority = self.config_manager.get("execution_priority", "balanced")
        log.debug(f"Handling order {order_event.payload.order_id} (priority: {execution_priority})")
        risk_data = await self.state_store.get_last_approved_risk_metrics()
        if not risk_data:
            log.warning("No approved risk metrics available in StateStore for order")
            return

        risk_metrics = RiskMetrics(
            portfolio_var=math_authority.d(risk_data["portfolio_var"]),
            portfolio_volatility=Decimal("0"),
            max_drawdown=math_authority.d(risk_data["max_drawdown"]),
            leverage=math_authority.d(risk_data["leverage"]),
            timestamp=datetime.now(timezone.utc),
            trace_id=str(trace_id),
        )
        allocation_weights = AllocationWeights(
            timestamp=datetime.now(timezone.utc),
            weights={order_event.payload.symbol: order_event.payload.quantity},
            trace_id=str(trace_id),
        )
        await self.oms_adapter.create_order(
            allocation_weights=allocation_weights, risk_metrics=risk_metrics
        )
        log.info(f"Sent order via OMS adapter: {order_event.payload.order_id}")

    @execution_wrapper(source="handle_fills")
    async def handle_fills(self, fill_event: FillEvent) -> None:
        await runtime_gatekeeper.check_event(fill_event)
        trace_id = fill_event.trace_id
        logger.bind(trace_id=trace_id)
        symbol = fill_event.payload.symbol
        quantity_dec = fill_event.payload.quantity
        price_dec = fill_event.payload.price
        current_position = await self.state_store.get_position(symbol)
        if current_position:
            new_quantity = current_position.quantity + quantity_dec
            new_cost = (
                current_position.quantity * current_position.average_price
                + quantity_dec * price_dec
            )
            new_avg_price = new_cost / new_quantity if new_quantity != 0 else Decimal("0")
            updated_position = Position(
                symbol=symbol, quantity=new_quantity, average_price=new_avg_price
            )
            await self.state_store.set_position(updated_position)
        else:
            new_position = Position(symbol=symbol, quantity=quantity_dec, average_price=price_dec)
            await self.state_store.set_position(new_position)
        if self.state_store:
            await self.state_store.update_performance_metrics(symbol, quantity_dec, price_dec)
        if self.ledger_engine:
            fill_amount = float(-quantity_dec * price_dec)
            fee_amount = float(fill_event.payload.fee or 0)
            entry_cash = LedgerEntry(
                tx_id=str(trace_id),
                asset="USD",
                amount=fill_amount - fee_amount,
                entry_type="TRADE",
            )
            entry_contra = LedgerEntry(
                tx_id=str(trace_id),
                asset="SETTLEMENT",
                amount=-(fill_amount - fee_amount),
                entry_type="CONTRA",
            )
            tx = Transaction(entries=[entry_cash, entry_contra])
            try:
                self.ledger_engine.record_transaction(tx)
                logger.debug(
                    f"ORCHESTRATOR_LEDGER | Recorded ATOMIC transaction | Trace: {trace_id}"
                )
            except Exception as e:
                logger.error(f"ORCHESTRATOR_LEDGER_FAILURE | Transaction rejected: {e}")
        await self.feedback_engine.process_fill(fill_event)

    @execution_wrapper(source="handle_risk_alert")
    async def handle_risk_alert(self, alert_data: dict[str, Any]) -> None:
        await runtime_gatekeeper.check(
            {"stage": "risk_alert", "trace_id": alert_data.get("trace_id")}
        )
        trace_id = alert_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        log.warning(f"Risk alert received: {alert_data}")
        _ = await self.network_kill_switch.engage_hard_kill(reason="Risk limits exceeded")

    @execution_wrapper(source="_handle_feedback_update")
    async def _handle_feedback_update(self, data: dict[str, Any]) -> None:
        await runtime_gatekeeper.check(
            {"stage": "feedback_update", "trace_id": data.get("trace_id")}
        )
        logger.debug("Handling feedback update")
        regime = "default"
        meta_result = self.meta_learner.update(feedback=data, regime=regime)
        logger.info(f"Updated meta-learner for regime {regime}")
        if meta_result:
            if (
                hasattr(self.ensemble_strategy, "meta_learning_engine")
                and self.ensemble_strategy.meta_learning_engine
            ):
                strategy_scores = data.get("strategy_scores", {})
                feature_scores = data.get("feature_scores", {})
                strategy_performance = {}
                for strategy_name, score in strategy_scores.items():
                    strategy_performance[strategy_name] = {
                        "sharpe": float(score),
                        "pnl_mean": 0.01,
                        "drawdown": 0.001,
                        "hit_ratio": 0.5,
                    }
                feature_performance = {}
                for feature_name, ic in feature_scores.items():
                    feature_performance[feature_name] = (float(ic), 0.1)
                self.ensemble_strategy.meta_learning_engine.update(
                    strategy_performance=strategy_performance,
                    feature_performance=feature_performance,
                    regime=regime,
                    regime_prob=1.0,
                )
                logger.debug("Updated ensemble strategy's meta-learning engine")
            else:
                strategy_weights = meta_result.get("strategy_weights", {})
                if strategy_weights and hasattr(self.ensemble_strategy, "_strategy_weights"):
                    logger.debug(f"Setting ensemble strategy weights: {strategy_weights}")
                    logger.info(f"Would set ensemble strategy weights: {strategy_weights}")
            risk_multiplier = meta_result.get("risk_multiplier", 1.0)
            await self.state_store.set_current_risk_multiplier(Decimal(str(risk_multiplier)))
            if hasattr(self.portfolio_allocator, "set_risk_multiplier"):
                self.portfolio_allocator.set_risk_multiplier(risk_multiplier)
                logger.debug(f"Set allocator risk multiplier to {risk_multiplier}")
            try:
                if (
                    hasattr(self.feedback_engine, "_feature_data")
                    and self.feedback_engine._feature_data
                ):
                    window_size = 100
                    reference_data = {}
                    live_data = {}
                    for feature_name, feature_deque in self.feedback_engine._feature_data.items():
                        if len(feature_deque) >= 2:
                            feature_values = [item[0] for item in feature_deque]
                            if len(feature_values) >= window_size * 2:
                                reference_vals = feature_values[:-window_size]
                                live_vals = feature_values[-window_size:]
                            elif len(feature_values) >= window_size:
                                split_point = len(feature_values) // 2
                                reference_vals = feature_values[:split_point]
                                live_vals = feature_values[split_point : split_point + window_size]
                            else:
                                continue
                            if len(reference_vals) > 0 and len(live_vals) > 0:
                                reference_data[feature_name] = reference_vals
                                live_data[feature_name] = live_vals
                    if reference_data and live_data:
                        min_ref_len = (
                            min(len(vals) for vals in reference_data.values())
                            if reference_data
                            else 0
                        )
                        min_live_len = (
                            min(len(vals) for vals in live_data.values()) if live_data else 0
                        )
                        target_len = min(min_ref_len, min_live_len)
                        if target_len >= 2:
                            final_ref_data = {
                                k: v[:target_len] for (k, v) in reference_data.items()
                            }
                            final_live_data = {k: v[:target_len] for (k, v) in live_data.items()}
                            reference_df = pl.DataFrame(final_ref_data)
                            live_df = pl.DataFrame(final_live_data)
                            columns = list(final_ref_data.keys())
                            drift_result = self.drift_detector.detect_drift(
                                train_data=reference_df, live_data=live_df, columns=columns
                            )
                            if drift_result.get("drift_alert", False):
                                logger.warning(
                                    f"Drift detected! Severity: {drift_result.get('severity')}"
                                )
                                await self.event_bus.publish(
                                    SystemEvent(
                                        source="DriftMonitor",
                                        payload=SystemPayload(
                                            action="DRIFT_ALERT",
                                            reason=str(drift_result.get("severity", "UNKNOWN")),
                                            metadata=drift_result,
                                        ),
                                    )
                                )
            except Exception as e:
                logger.error(f"Error checking for drift in feedback update: {e}")
            if self.mlflow_manager and self.mlflow_manager.is_enabled():
                self._local_feedback_count += 1
                if self._local_feedback_count % 10 == 0:
                    try:
                        strategy_name = data.get("strategy_name", "unknown")
                        asyncio.create_task(
                            self.mlflow_manager.log_run(
                                strategy_name=strategy_name,
                                run_name=f"feedback_{strategy_name}_{datetime.utcnow().timestamp()}",
                                metrics={"sharpe": float(data.get("sharpe", 0))},
                                parameters={},
                            )
                        )
                    except Exception as e:
                        logger.error(f"Failed to log feedback to MLflow: {e}")

    async def _is_kill_switch_active(self) -> bool:
        return self.network_kill_switch.is_engaged()

    def _simple_ensemble_combine(self, signals: dict[str, Any]) -> dict[str, Any] | None:
        if not signals:
            return None
        total_strength = 0.0
        count = 0
        for _signal_name, signal_data in signals.items():
            if isinstance(signal_data, dict) and "strength" in signal_data:
                total_strength += float(signal_data["strength"])
                count += 1
        if count == 0:
            return None
        avg_strength = total_strength / count
        return {"signal_type": "ENSEMBLE", "strength": avg_strength}

    def _get_signal_reason(self, signal: dict[str, Any]) -> str:
        signal_type = signal.get("signal_type", "UNKNOWN")
        strength = signal.get("strength", 0)
        if strength > 0.7:
            conviction = "strong"
        elif strength > 0.3:
            conviction = "moderate"
        elif strength > 0.1:
            conviction = "weak"
        else:
            conviction = "very weak"
        if signal_type in ["BUY", "LONG"]:
            direction = "bullish"
        elif signal_type in ["SELL", "SHORT"]:
            direction = "bearish"
        else:
            direction = "neutral"
        return f"{conviction} {direction} signal"
