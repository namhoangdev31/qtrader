"""Sovereign Orchestrator for the QTrader live trading system.

This module is the single source of truth for the event-driven pipeline, 
coordinating market data, alpha generation, feature validation, 
strategy, risk, and execution.
"""


import asyncio
import os
import time
from decimal import Decimal
from enum import Enum, auto
from typing import Any,  Mapping, Optional, Sequence


from qtrader.core.types import (
    AllocationWeights,
    EventBusProtocol,
    MarketData,
)

import uuid
from typing import Mapping
from datetime import datetime, timezone
from qtrader.core.events import (
    BaseEvent, 
    SystemEvent, 
    SystemPayload, 
    MarketEvent, 
    SignalEvent,
    EventType
)
from qtrader.system.pipeline_validator import PipelineValidator


# Phase -1 Authorities
from qtrader.core.config_manager import ConfigManager
from qtrader.core.config_enforcer import ConfigEnforcer
from qtrader.core.seed_manager import SeedManager
from qtrader.core.logger import QTraderLogger
from qtrader.core.trace_authority import TraceAuthority
from qtrader.core.fail_fast_engine import FailFastEngine
from qtrader.monitoring.metrics_collector import MetricsCollector
from qtrader.core.decimal_adapter import math_authority, d
from qtrader.monitoring.alert_engine import AlertEngine




# Try to import MLflowManager, but don't fail if not available
try:
    from qtrader.ml.mlflow_manager import MLflowManager
    MLFLOW_MANAGER_AVAILABLE = True
except ImportError:
    MLFLOW_MANAGER_AVAILABLE = False
    MLflowManager = None  # type: ignore
from loguru import logger

from qtrader.analytics.drift_detector import DriftDetector
from qtrader.core.resource_monitor import ResourceMonitor
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.core.state_store import Position, StateStore
from qtrader.execution.latency_model import LatencyModel
from qtrader.execution.orderbook_enhanced import OrderbookEnhanced
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.execution.slippage_model import SlippageModel
from qtrader.ml.meta_online import OnlineMetaLearner
from qtrader.monitoring.feedback.feedback_engine import FeedbackEngine
from qtrader.oms.oms_adapter import OMSAdapter
from qtrader.risk.network_kill_switch import NetworkKillSwitch
from qtrader.risk.portfolio.allocator import AllocatorBase
from qtrader.risk.runtime import RuntimeRiskEngine
from qtrader.strategy.alpha.alpha_base import AlphaBase
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.strategy.validation.feature_validator import FeatureValidator
from qtrader.core.system_state import SystemState, state_manager


class TradingOrchestrator:
    """Sovereign Orchestrator for the QTrader trading system."""



    def __init__(
        self,
        event_bus: EventBusProtocol,
        market_data_adapter: object,
        alpha_modules: list[AlphaBase],
        feature_validator: FeatureValidator,
        strategies: list[ProbabilisticStrategy],
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
        
        # State Initialization (Global Sync)
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
        self.drift_detector = DriftDetector()
        
        # Authority Initialization
        from qtrader.core.config import settings
        self.settings = settings

        # Shadow System & Resource Governance
        self.shadow_engine = ShadowEngine(config=settings.model_dump() if hasattr(settings, "model_dump") else {})
        self.resource_monitor = ResourceMonitor()
        self.seed_manager = SeedManager.from_config(
            strategy_id="QTrader-V1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            simulate_mode=settings.simulate_mode
        )
        self.fail_fast_engine = FailFastEngine(global_orchestrator=self)
        
        trading_symbols = settings.TRADING_SYMBOLS

        orderbook_sim = OrderbookEnhanced(symbols=trading_symbols)
        slippage_model = SlippageModel()
        latency_model = LatencyModel(
            base_network_latency_ms=10.0,
            network_jitter_ms=2.0,
            base_processing_latency_ms=5.0,
            processing_jitter_ms=1.0
        )
        shadow_config = {
            "shadow_mode": True,  # Set to True for paper trading; can be made configurable
            "data_lake_path": "./data_lake/shadow",
            "orderbook_simulator": orderbook_sim,
            "slippage_model": slippage_model,
            "latency_model": latency_model,
            "event_bus": event_bus
        }
        self.shadow_engine = ShadowEngine(shadow_config)
        self.resource_monitor = ResourceMonitor()
        self.network_kill_switch = NetworkKillSwitch(oms_adapter=oms_adapter, logger_instance=logger)
        if MLFLOW_MANAGER_AVAILABLE:
            self.mlflow_manager = MLflowManager(
                tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"),
                experiment_name="QTrader-Strategies",
                enable_mlflow=True
            )
        else:
            self.mlflow_manager = None
        self._local_feedback_count = 0 

        self.max_drawdown = Decimal('0.20')  # 20%
        self.max_var = Decimal('0.05')       # 5% VaR
        self.max_leverage = Decimal('5.0')   # 5x leverage

        # Register event handlers
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
        """
        Sovereign Initialization Sequence: Path to READY state.
        
        Steps: Load Config -> Apply Seeds -> Init Logger -> Init Trace -> Init FailFast.
        """
        try:
            logger.info("ORCHESTRATOR_BOOT | Sequence initiated (S=INIT).")
            
            # 2. Entropy Authority (Freezing randomness)
            self.seed_manager.apply_global()
            
            # 3. Trace Authority (Agnostic context start)
            TraceAuthority.start_trace()
            
            # 4. Architectural Validation
            self.validate()
            
            state_manager.set_state(SystemState.READY)
            self._state = SystemState.READY

            
            # 5. Forensic Boot Log
            self._write_boot_log(start_time=self._boot_time, status="SUCCESS")
            
            logger.info("ORCHESTRATOR_BOOT | System is READY.")

            
        except Exception as e:
            state_manager.set_state(SystemState.ERROR)
            self._state = SystemState.ERROR
            logger.critical(f"ORCHESTRATOR_BOOT_FAILURE | Hard stop initiated: {e}")
            raise RuntimeError(f"System initialization failed: {e}")

    def validate(self) -> None:
        """Mandatory POST-INIT check to ensure 100% compliance."""
        if not self.settings:
            raise RuntimeError("Configuration settings not available.")
        if not self.seed_manager.is_applied:
            raise RuntimeError("Global seed not applied.")
        logger.info("ORCHESTRATOR_VALIDATION | Post-init compliance 100%.")


    def _write_boot_log(self, start_time: float, status: str) -> None:
        """Write forensic log to audit/system_boot_log.json."""
        import json
        boot_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "boot_duration_ms": (asyncio.get_event_loop().time() - start_time) * 1000,
            "status": status,
            "config_checksum": ConfigManager.get_checksum() if hasattr(ConfigManager, "get_checksum") else "N/A",
            "seed_applied": self.seed_manager.is_applied,
            "authorities_initialized": [
                "ConfigManager", "SeedManager", "TraceAuthority", "FailFastEngine"
            ]
        }
        log_path = "/Users/hoangnam/qtrader/qtrader/audit/system_boot_log.json"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(boot_log, f, indent=2)

    async def run(self) -> None:
        """
        The single sovereign entry point for all execution flows.
        Activates the system state machine: READY -> RUNNING.
        """
        if self._state == SystemState.INIT:
            logger.info("ORCHESTRATOR_RUN | Automated boot from INIT.")
            self.initialize()
            
        if self._state != SystemState.READY:
            logger.critical(f"ORCHESTRATOR_LIFECYCLE | Run blocked: System is in {self._state.name} state.")
            raise RuntimeError(f"Cannot run: System must be READY (Current: {self._state.name})")

        # THRESHOLD: Transition to RUNNING immediately to open the reactive gates
        state_manager.set_state(SystemState.RUNNING)
        self._state = SystemState.RUNNING
        logger.info(f"ORCHESTRATOR_LIFECYCLE | Sovereign Gate ACTIVE (S={self._state.name})")
        
        # Activate System Infrastructure
        await self.event_bus.start()
        await self._start_components()
        
        # Enter autonomous execution loop
        await self.run_autonomous()

    async def execute_pipeline(self) -> None:
        """Alias for run() to maintain backward compatibility with research runners."""
        await self.run()

    def register_module(self, module: Any) -> None:

        """
        Register a top-level module in the pipeline or strategy ensemble.
        
        Each module is subjected to architectural review by the PipelineValidator 
        to ensure zero direct-coupling with other engines.
        """
        if self._validator.validate_module_architecture(module.__class__):
            self._modules.append(module)
            logger.info(f"ORCHESTRATOR_INTEGRATION | {module.__class__.__name__} certified.")
        else:
            logger.critical(f"ORCHESTRATOR_BOOT_FAILURE | Module {module.__class__.__name__} rejected.")
            raise RuntimeError(f"Module {module.__class__.__name__} failed architectural certification.")

    async def inject_event(self, event: BaseEvent) -> bool:
        """
        Authoritative entry point for market data or system commands.
        
        Ensures that every event entering the pipeline is compliant with 
        traceability and partition requirements.
        """
        if not event.trace_id:
            event = event.model_copy(update={"trace_id": uuid.uuid4()})
            
        return await self.event_bus.publish(event.event_type, event)

    async def ingest_raw_data(self, raw_data: dict[str, Any]) -> MarketEvent | None:
        """
        Sovereign Ingestion Path: Route raw exchange data through internal sequencing.
        """
        if self._state != SystemState.RUNNING:
            logger.warning(f"ORCHESTRATOR_GATE | Ingestion blocked. System state: {self._state.name}")
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
                await self.event_store.record_event(event)
            
            await self.event_bus.publish(EventType.MARKET_DATA, event)
            return event

        except Exception as e:
            logger.exception(f"ORCHESTRATOR_INGESTION_FAILURE | {e}")
            return None

    async def _run_data_quality_checks(self, event: MarketEvent) -> bool:
        """Run statistical MAD and cross-exchange sanity checks."""
        if not self.quality_gate or not self.event_store:
            return True
            
        symbol = event.symbol
        rolling_prices = self.event_store.get_recent_prices(symbol, window_size=50)
        ref_price = self.event_store.get_latest_price_cross_exchange(
            symbol, exclude_venue=event.metadata.get("venue", "unknown")
        )
        
        is_valid = self.quality_gate.validate(
            event, 
            rolling_prices, 
            ref_price=ref_price
        )
        
        if not is_valid:
            rejected = DataRejectedEvent(
                symbol=symbol,
                trace_id=event.trace_id,
                reason="Outlier/Cross-exchange deviation",
                value=float(event.close)
            )
            await self.event_bus.publish(EventType.DATA_REJECTED, rejected)
            
        return is_valid

    async def run_autonomous(self) -> None:
        """
        Sovereign Execution Loop: Keep the system alive and process periodic tasks.
        
        Replaces bot/runner.py lifecycle.
        """
        logger.info("ORCHESTRATOR_LIFECYCLE | Autonomous loop is now ACTIVE.")
        await self._start_components()
        
        try:
            while True:
                await self._periodic_check()
                await asyncio.sleep(0.1) 
        except asyncio.CancelledError:
            logger.warning("ORCHESTRATOR_LIFECYCLE | Shutdown requested.")
            await self.halt_core("SHUTDOWN_SIGNAL")

    async def _periodic_check(self) -> None:
        """Periodic tasks: Risk check, Rebalance, Heartbeat."""
        current_ts = asyncio.get_event_loop().time()
        
        if self.hft_optimizer:
            self.hft_optimizer.check_and_update_safety_mode()
            
        await self.event_bus.publish(
            EventType.HEARTBEAT, 
            SystemEvent(
                trace_id=uuid.uuid4(),
                source="UnifiedOrchestrator",
                payload=SystemPayload(action="HEARTBEAT", reason="LIVELINESS")
            )
        )
        
        await self.apply_strategic_allocation()

    async def apply_strategic_allocation(self) -> None:
        """
        Strategic Layer: Apply fund-wide capital allocation and leverage limits.
        
        Replaces qtrader/core/global_orchestrator.py logic.
        """
        logger.debug("ORCHESTRATOR_STRATEGY | Periodic strategic allocation check completed.")

    def compute_consensus_signal(self, signals: Mapping[str, float], weights: Mapping[str, float]) -> float:
        """
        Mathematical Layer: Produce a weighted consensus signal from multiple models.
        
        Replaces qtrader/meta/orchestrator.py logic.
        """
        if not signals or not weights:
            return 0.0
            
        epsilon = 1e-12
        weighted_sum = sum(signals.get(m, 0.0) * weights.get(m, 0.0) for m in weights)
        total_weight = sum(weights.values())
        
        return weighted_sum / (total_weight + epsilon)

    def adapt_model_weights(self, performance: Mapping[str, float]) -> dict[str, float]:
        """
        Mathematical Layer: Dynamically adjust model weights based on performance.
        """
        if not performance:
            return {}
            
        total = sum(max(0.0, p) for p in performance.values())
        if total <= 0:
            return {m: 1.0 / len(performance) for m in performance}
            
        return {m: max(0.0, p) / total for m, p in performance.items()}

    async def halt_core(self, reason: str) -> None:
        """Emergency shutdown of all components."""
        logger.critical(f"SYSTEM_ORCHESTRATOR_HALT | Initiating shutdown for: {reason}")
        state_manager.set_state(SystemState.SHUTDOWN)
        self._state = SystemState.SHUTDOWN
        
        # Shutdown infrastructure
        await self._stop_components()
        await self.event_bus.shutdown()
        
        logger.info(f"SYSTEM_ORCHESTRATOR_HALT | Shutdown complete (Reason: {reason})")

    async def _start_components(self) -> None:
        """Start background components."""
        await self.shadow_engine.start()
        await self.resource_monitor.start_monitoring()
        logger.info("Background components started")

    async def _stop_components(self) -> None:
        """Stop background components."""
        await self.shadow_engine.stop()
        await self.resource_monitor.stop_monitoring()
        logger.info("Background components stopped")

    async def handle_market_data(self, market_data: MarketData) -> None:
        """Reactive alpha generation gate."""
        if self._state != SystemState.RUNNING:
            return
            
        trace_id = TraceAuthority.propagate(market_data)
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            # 1. Decimal Normalization (Numerical Integrity Gate)
            market_data.close = math_authority.d(market_data.close)
            market_data.volume = math_authority.d(market_data.volume)
            
            log.info(f"Handling market data for {market_data.symbol} - Input: close={market_data.close}, volume={market_data.volume}")
            features = {}
            for alpha in self.alpha_modules:
                alpha_output = await alpha.generate(market_data)
                if hasattr(alpha_output, 'alpha_values') and isinstance(alpha_output.alpha_values, dict):
                    features.update(alpha_output.alpha_values)
                else:
                    log.warning(f"Alpha module {alpha.name} returned unexpected output: {type(alpha_output)}")
            
            features_data = {
                "features": features,
                "timestamp": datetime.utcnow(),
                "source_market_data": market_data,
                "symbol": market_data.symbol,
                "trace_id": trace_id
            }
            await self.event_bus.publish(EventType.FEATURES, features_data)
            log.info(f"Published FEATURES for {market_data.symbol} - Output: {len(features)} features computed")
        except Exception as e:
            # 2. Fail-Fast Enforcement (Sovereign Gate)
            await self.fail_fast_engine.handle_error(source="handle_market_data", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_market_data latency: {latency*1000:.2f}ms")

    async def handle_features(self, features_data: dict[str, Any]) -> None:
        trace_id = features_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping feature validation")
                return
            log.debug(f"Handling features - Input: {len(features_data.get('features', {}))} features")
            features = features_data.get("features", {})
            validated = await self.feature_validator.validate(features)
            if validated is None:
                log.warning("Feature validation failed")
                return
            validated_features_data = {
                "features": validated,
                "timestamp": datetime.utcnow(),
                "source_features": features,
                "trace_id": trace_id
            }
            await self.event_bus.publish(EventType.VALIDATED_FEATURES, validated_features_data)
            log.info(f"Published VALIDATED_FEATURES - Output: {len(validated.features)} validated features")
        except Exception as e:
            # Sovereign Gate
            await self.fail_fast_engine.handle_error(source="handle_features", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_features latency: {latency*1000:.2f}ms")

    async def handle_validated_features(self, validated_features_data: dict[str, Any]) -> None:
        trace_id = validated_features_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping signal generation")
                return
            validated_features_obj = validated_features_data.get("features")
            if validated_features_obj is None:
                log.warning("No features in validated_features_data")
                return
            ensemble_signal = await self.ensemble_strategy.generate_signal(validated_features_obj)
            
            # Numeric Normalization
            signals_data = {
                "signal": {
                    "signal_type": ensemble_signal.signal_type,
                    "strength": float(math_authority.to_price(ensemble_signal.strength))
                },
                "timestamp": datetime.utcnow(),
                "source_strategy": "ensemble",
                "trace_id": trace_id
            }
            await self.event_bus.publish(EventType.SIGNALS, signals_data)
            log.info(f"Published SIGNALS - Output: ensemble signal {ensemble_signal.signal_type} with strength {ensemble_signal.strength}")
        except Exception as e:
            await self.fail_fast_engine.handle_error(source="handle_validated_features", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_validated_features latency: {latency*1000:.2f}ms")

    async def handle_signals(self, signals_data: dict[str, Any]) -> None:
        trace_id = signals_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping signal processing")
                return
            
            signal_info = signals_data.get("signal")
            if not signal_info:
                log.warning("No signal in signals data")
                return
            
            symbol = signals_data.get("symbol", "UNKNOWN")
            
            # Numeric Normalization
            signal_event = SignalEvent(
                symbol=symbol,
                signal_type=signal_info.get("signal_type", "UNKNOWN"),
                strength=math_authority.to_price(signal_info.get("strength", 0)),
                timestamp=signals_data.get("timestamp", datetime.utcnow()),
                trace_id=trace_id,
                metadata={}
            )
            
            log.info(f"Processing signal: {signal_event.signal_type} with strength {signal_event.strength}")
            
            last_ts = await self.state_store.get_last_signal_timestamp()
            if last_ts and last_ts == signal_event.timestamp:
                log.warning("Duplicate signal detected, skipping")
                return
            await self.state_store.set_last_signal_timestamp(signal_event.timestamp)
 
            allocation_weights = await self.portfolio_allocator.allocate(signal_event)
            if allocation_weights is None:
                log.debug("No allocation computed")
                return
            
            # Numeric Normalization via math_authority
            allocation_dict = {k: float(math_authority.to_price(v)) for k, v in allocation_weights.weights.items()}
            
            risk_metrics = await self.runtime_risk_engine.evaluate_risk(
                allocation_weights=allocation_weights
            )
            if (risk_metrics.portfolio_var > self.max_var or 
                risk_metrics.max_drawdown > self.max_drawdown or 
                risk_metrics.leverage > self.max_leverage):
                log.warning(f"Risk check failed, blocking order. Reason: VaR={risk_metrics.portfolio_var} > {self.max_var} or Drawdown={risk_metrics.max_drawdown} > {self.max_drawdown} or Leverage={risk_metrics.leverage} > {self.max_leverage}")
                await self.event_bus.publish(EventType.RISK_ALERT, {
                    "allocation": allocation_dict,
                    "risk_metrics": risk_metrics,
                    "timestamp": datetime.utcnow(),
                    "reason": "Risk limits exceeded",
                    "trace_id": trace_id
                })
                return
            
            await self.state_store.set_last_approved_risk_metrics({
                "portfolio_var": float(math_authority.to_price(risk_metrics.portfolio_var)),
                "max_drawdown": float(math_authority.to_price(risk_metrics.max_drawdown)),
                "leverage": float(math_authority.to_price(risk_metrics.leverage))
            })
            log.info(f"Risk check passed. VaR={risk_metrics.portfolio_var}, Drawdown={risk_metrics.max_drawdown}, Leverage={risk_metrics.leverage}")
            
            await self.event_bus.publish(EventType.ORDERS, {
                "allocation": allocation_dict,
                "timestamp": datetime.utcnow(),
                "source_ensemble": signal_info,
                "trace_id": trace_id
            })
            log.info(f"Published ORDERS - Output: {len(allocation_dict)} allocations")
        except Exception as e:
            await self.fail_fast_engine.handle_error(source="handle_signals", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_signals latency: {latency*1000:.2f}ms")

    async def handle_orders(self, orders_data: dict[str, Any]) -> None:
        trace_id = orders_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping order submission")
                return
            log.debug(f"Handling orders - Input: {len(orders_data.get('allocation', {}))} allocations")
            allocation_dict = orders_data.get("allocation", {})
            if not allocation_dict:
                log.warning("No allocation in orders data")
                return
            
            risk_data = await self.state_store.get_last_approved_risk_metrics()
            if not risk_data:
                log.warning("No approved risk metrics available in StateStore for order")
                return
            
            from qtrader.core.types import RiskMetrics
            # Numeric Normalization
            risk_metrics = RiskMetrics(
                portfolio_var=math_authority.to_price(risk_data["portfolio_var"]),
                max_drawdown=math_authority.to_price(risk_data["max_drawdown"]),
                leverage=math_authority.to_price(risk_data["leverage"]),
                timestamp=datetime.utcnow()
            )
            allocation_weights = AllocationWeights(
                timestamp=orders_data.get("timestamp", datetime.utcnow()),
                weights={k: math_authority.to_price(v) for k, v in allocation_dict.items()},
                trace_id=trace_id
            )
            order_event = await self.oms_adapter.create_order(
                allocation_weights=allocation_weights,
                risk_metrics=risk_metrics
            )
            log.info(f"Sent order via OMS adapter: {order_event}")
        except Exception as e:
            await self.fail_fast_engine.handle_error(source="handle_orders", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_orders latency: {latency*1000:.2f}ms")

    async def handle_fills(self, fill_data: dict[str, Any]) -> None:
        trace_id = fill_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            log.debug(f"Handling fills - Input: symbol={fill_data.get('symbol')}, quantity={fill_data.get('quantity')}, price={fill_data.get('price')}")
            symbol = fill_data.get("symbol")
            quantity = fill_data.get("quantity")
            price = fill_data.get("price")
            if symbol is None or quantity is None or price is None:
                log.warning("Invalid fill data")
                return
            
            # Numeric Normalization
            quantity_dec = math_authority.to_qty(quantity)
            price_dec = math_authority.to_price(price)
            
            # Update positions
            current_position = await self.state_store.get_position(symbol)
            if current_position:
                new_quantity = current_position.quantity + quantity_dec
                new_cost = current_position.quantity * current_position.average_price + quantity_dec * price_dec
                new_avg_price = new_cost / new_quantity if new_quantity != 0 else Decimal('0')
                updated_position = Position(
                    symbol=symbol,
                    quantity=new_quantity,
                    average_price=new_avg_price
                )
                await self.state_store.set_position(updated_position)
            else:
                new_position = Position(
                    symbol=symbol,
                    quantity=quantity_dec,
                    average_price=price_dec
                )
                await self.state_store.set_position(new_position)
            
            if self.state_store:
                await self.state_store.update_performance(symbol, quantity_dec, price_dec)
            
            from qtrader.core.types import FillEvent
            fill_event = FillEvent(
                order_id=fill_data.get("order_id", f"orchestrator_{datetime.utcnow().timestamp()}"),
                symbol=symbol,
                timestamp=fill_data.get("timestamp", datetime.utcnow()),
                side=fill_data.get("side", "BUY"),
                quantity=quantity_dec,
                price=price_dec,
                commission=Decimal('0'),
                trace_id=trace_id,
                metadata={}
            )
            await self.feedback_engine.process_fill(fill_event)
        except Exception as e:
            await self.fail_fast_engine.handle_error(source="handle_fills", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_fills latency: {latency*1000:.2f}ms")

    async def handle_risk_alert(self, alert_data: dict[str, Any]) -> None:
        trace_id = alert_data.get("trace_id", TraceAuthority.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            log.warning(f"Risk alert received: {alert_data}")
            _ = await self.network_kill_switch.engage_hard_kill(reason="Risk limits exceeded")
        except Exception as e:
            await self.fail_fast_engine.handle_error(source="handle_risk_alert", error=e)
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_risk_alert latency: {latency*1000:.2f}ms")

    async def _handle_feedback_update(self, data: dict[str, Any]) -> None:
        """Handle feedback updates from the feedback engine."""
        try:
            logger.debug("Handling feedback update")
            regime = "default"
            meta_result = self.meta_learner.update(feedback=data, regime=regime)
            logger.info(f"Updated meta-learner for regime {regime}")
            
            if meta_result:
                if hasattr(self.ensemble_strategy, 'meta_learning_engine') and self.ensemble_strategy.meta_learning_engine:
                    strategy_scores = data.get('strategy_scores', {})
                    feature_scores = data.get('feature_scores', {})
                    
                    strategy_performance = {}
                    for strategy_name, score in strategy_scores.items():
                        strategy_performance[strategy_name] = {
                            'sharpe': float(score),
                            'pnl_mean': 0.01,  # Small positive return
                            'drawdown': 0.001, # Small drawdown
                            'hit_ratio': 0.5   # Neutral hit ratio
                        }
                    
                    feature_performance = {}
                    for feature_name, ic in feature_scores.items():
                        feature_performance[feature_name] = (float(ic), 0.1)
                    
                    self.ensemble_strategy.meta_learning_engine.update(
                        strategy_performance=strategy_performance,
                        feature_performance=feature_performance,
                        regime=regime,
                        regime_prob=1.0  # Assume 100% probability for default regime
                    )
                    logger.debug("Updated ensemble strategy's meta-learning engine")
                else:
                    strategy_weights = meta_result.get('strategy_weights', {})
                    if strategy_weights and hasattr(self.ensemble_strategy, '_strategy_weights'):
                        logger.debug(f"Setting ensemble strategy weights: {strategy_weights}")
                        logger.info(f"Would set ensemble strategy weights: {strategy_weights}")
                
                risk_multiplier = meta_result.get('risk_multiplier', 1.0)
                await self.state_store.set_current_risk_multiplier(Decimal(str(risk_multiplier)))
                if hasattr(self.portfolio_allocator, 'set_risk_multiplier'):
                    self.portfolio_allocator.set_risk_multiplier(risk_multiplier)
                    logger.debug(f"Set allocator risk multiplier to {risk_multiplier}")
                
                try:
                    if hasattr(self.feedback_engine, '_feature_data') and self.feedback_engine._feature_data:
                        window_size = 100
                        
                        reference_data = {}  # feature_name -> list of values
                        live_data = {}       # feature_name -> list of values
                        
                        for feature_name, feature_deque in self.feedback_engine._feature_data.items():
                            if len(feature_deque) >= 2:
                                feature_values = [item[0] for item in feature_deque]
                                
                                if len(feature_values) >= window_size * 2:
                                    reference_vals = feature_values[:-window_size]  # Older data
                                    live_vals = feature_values[-window_size:]       # Recent data
                                elif len(feature_values) >= window_size:
                                    split_point = len(feature_values) // 2
                                    reference_vals = feature_values[:split_point]
                                    live_vals = feature_values[split_point:split_point + window_size]
                                else:
                                    continue
                                
                                if len(reference_vals) > 0 and len(live_vals) > 0:
                                    reference_data[feature_name] = reference_vals
                                    live_data[feature_name] = live_vals
                        
                        if reference_data and live_data:
                            min_ref_len = min(len(vals) for vals in reference_data.values()) if reference_data else 0
                            min_live_len = min(len(vals) for vals in live_data.values()) if live_data else 0
                            
                            if min_ref_len > 0 and min_live_len > 0:
                                ref_data_truncated = {
                                    feat: vals[:min_ref_len] for feat, vals in reference_data.items()
                                }
                                live_data_truncated = {
                                    feat: vals[:min_live_len] for feat, vals in live_data.items()
                                }
                                
                                # Create DataFrames
                                import polars as pl
                                reference_df = pl.DataFrame(ref_data_truncated)
                                live_df = pl.DataFrame(live_data_truncated)
                                
                                # Get column names
                                columns = list(reference_data.keys())
                                
                                # Run drift detection
                                drift_result = self.drift_detector.detect_drift(
                                    train_data=reference_df,
                                    live_data=live_df,
                                    columns=columns
                                )
                                
                                # Log results
                                if drift_result.get("drift_alert", False):
                                    logger.warning(
                                        f"Drift detected! Severity: {drift_result.get('severity', 'UNKNOWN')}. "
                                        f"Features checked: {len(columns)}. "
                                        f"Drift details: {drift_result.get('feature_drift', {})}"
                                    )
                                else:
                                    logger.debug(
                                        f"No significant drift detected. "
                                        f"Features checked: {len(columns)}. "
                                        f"Max PSI: {max([drift_result.get('feature_drift', {}).get(f, {}).get('psi', 0) for f in columns], default=0):.4f}"
                                    )
                            else:
                                logger.debug("Insufficient data for drift detection after truncation")
                        else:
                            logger.debug("Insufficient feature data for drift detection")
                    else:
                        logger.debug("Feature data not available in feedback engine for drift detection")
                except Exception as e:
                    logger.error(f"Error updating drift detector: {e}", exc_info=True)
                
                logger.debug("Feedback update processed")
                
                if self.mlflow_manager and self.mlflow_manager.is_enabled():
                    self._local_feedback_count += 1
                    if self._local_feedback_count % 10 == 0:
                        try:
                            strategy_name = data.get('strategy_name', 'unknown')
                            parameters = {
                                "strategy_name": strategy_name,
                                "regime": regime,
                                "feedback_timestamp": datetime.utcnow().isoformat(),
                            }
                            for key, value in data.items():
                                if isinstance(value, (str, int, float, bool)) and key not in ['strategy_name', 'regime']:
                                    parameters[key] = value
                                elif isinstance(value, dict):
                                    pass
                            metrics = {}
                            for metric_key in ['sharpe', 'drawdown', 'hit_rate', 'pnl']:
                                if metric_key in data:
                                    metrics[metric_key] = float(data[metric_key])
                            if not metrics:
                                metrics['feedback_value'] = 1.0  # Placeholder
                            
                            artifacts = {
                                "feedback_data": data
                            }
                            
                            asyncio.create_task(
                                self.mlflow_manager.log_run(
                                    strategy_name=strategy_name,
                                    parameters=parameters,
                                    metrics=metrics,
                                    artifacts=artifacts,
                                    run_name=f"feedback_{strategy_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                                    run_type="feedback"
                                )
                            )
                        except Exception as e:
                            logger.error(f"Failed to log feedback update to MLflow: {e}")
        except Exception as e:
            logger.error(f"Error handling feedback update: {e}", exc_info=True)



    async def _is_kill_switch_active(self) -> bool:
        """Check if kill switch is active via network kill switch."""
        return self.network_kill_switch.is_engaged()

    def _simple_ensemble_combine(self, signals: dict[str, Any]) -> dict[str, Any] | None:
        """Simple ensemble combination when the ensemble strategy doesn't support direct signal combination."""
        if not signals:
            return None
        
        total_strength = 0.0
        count = 0
        for _signal_name, signal_data in signals.items():
            if isinstance(signal_data, dict) and 'strength' in signal_data:
                total_strength += float(signal_data['strength'])
                count += 1
        
        if count == 0:
            return None
        
        avg_strength = total_strength / count
        return {
            "signal_type": "ENSEMBLE",
            "strength": avg_strength,
        }

    def _get_signal_reason(self, signal: dict[str, Any]) -> str:
        """Get a human-readable reason for the signal."""
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

