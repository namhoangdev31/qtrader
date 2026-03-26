"""Orchestrator for the QTrader live trading system.

This module coordinates the event-driven pipeline: market data -> alpha generation ->
feature validation -> strategy -> risk -> execution.
"""

import asyncio
import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from qtrader.core.types import (
    AllocationWeights,
    EventBusProtocol,
    EventType,
    MarketData,
    SignalEvent,
)

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
from qtrader.core.state_store import Position, StateStore
from qtrader.core.trace import TraceManager
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


class TradingOrchestrator:
    """Main orchestrator for the QTrader trading system."""

    def __init__(
        self,
        event_bus: EventBusProtocol,
        market_data_adapter: object,  # Not used in handlers but kept for interface compatibility
        alpha_modules: list[AlphaBase],
        feature_validator: FeatureValidator,
        strategies: list[ProbabilisticStrategy],
        ensemble_strategy: EnsembleStrategy,
        portfolio_allocator: AllocatorBase,
        runtime_risk_engine: RuntimeRiskEngine,
        oms_adapter: OMSAdapter,
        state_store: StateStore | None = None,
    ) -> None:
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
        # Initialize feedback engine
        self.feedback_engine = FeedbackEngine(event_bus=event_bus)
        # Initialize meta-learner for dynamic strategy/feature weighting and risk adjustment
        self.meta_learner = OnlineMetaLearner()
        # Initialize drift detector for monitoring data and model drift
        self.drift_detector = DriftDetector()
        # Initialize shadow engine for paper trading simulation
        # Create required components for shadow engine
        # Use symbols from global config
        from qtrader.core.config import Config
        trading_symbols = Config.TRADING_SYMBOLS
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
        # Initialize resource monitor for latency/memory control
        self.resource_monitor = ResourceMonitor()
        # Initialize network-level kill switch for instant risk containment
        self.network_kill_switch = NetworkKillSwitch(oms_adapter=oms_adapter, logger_instance=logger)
        # Initialize MLflow manager for experiment tracking
        if MLFLOW_MANAGER_AVAILABLE:
            self.mlflow_manager = MLflowManager(
                tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"),
                experiment_name="QTrader-Strategies",
                enable_mlflow=True
            )
        else:
            self.mlflow_manager = None
        # Current risk multiplier from meta-learner (default 1.0)
        self.current_risk_multiplier = Decimal('1.0')
        # Counter for feedback updates to control logging frequency
        self._feedback_update_count = 0

        # State limits (example values - should be configurable via constructor or config)
        self.max_drawdown = Decimal('0.20')  # 20%
        self.max_var = Decimal('0.05')       # 5% VaR
        self.max_leverage = Decimal('5.0')   # 5x leverage

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(EventType.MARKET_DATA, self.handle_market_data)
        self.event_bus.subscribe(EventType.FEATURES, self.handle_features)
        self.event_bus.subscribe(EventType.VALIDATED_FEATURES, self.handle_validated_features)
        self.event_bus.subscribe(EventType.SIGNALS, self.handle_signals)
        self.event_bus.subscribe(EventType.ORDERS, self.handle_orders)
        self.event_bus.subscribe(EventType.FILLS, self.handle_fills)
        self.event_bus.subscribe(EventType.RISK_ALERT, self.handle_risk_alert)
        # Subscribe to feedback updates for meta-learning and drift detection
        self.event_bus.subscribe(EventType.FEEDBACK_UPDATE, self._handle_feedback_update)

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
        trace_id = TraceManager.propagate(market_data)
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            log.info(f"Handling market data for {market_data.symbol} - Input: close={market_data.close}, volume={market_data.volume}")
            # Compute alpha features from all modules
            features = {}
            for alpha in self.alpha_modules:
                # Assuming alpha.generate returns an AlphaOutput
                alpha_output = await alpha.generate(market_data)
                if hasattr(alpha_output, 'alpha_values') and isinstance(alpha_output.alpha_values, dict):
                    features.update(alpha_output.alpha_values)
                else:
                    log.warning(f"Alpha module {alpha.name} returned unexpected output: {type(alpha_output)}")
            
            # Publish FEATURES event with symbol tracking
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
            log.error(f"Error in handle_market_data for {getattr(market_data, 'symbol', 'UNKNOWN')}: {e}")
            # Fallback: do not publish features
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_market_data latency: {latency*1000:.2f}ms")

    async def handle_features(self, features_data: dict[str, Any]) -> None:
        trace_id = features_data.get("trace_id", TraceManager.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping feature validation")
                return
            log.debug(f"Handling features - Input: {len(features_data.get('features', {}))} features")
            features = features_data.get("features", {})
            # Validate features
            validated = await self.feature_validator.validate(features)
            if validated is None:
                log.warning("Feature validation failed")
                return
            # Publish VALIDATED_FEATURES event
            validated_features_data = {
                "features": validated,
                "timestamp": datetime.utcnow(),
                "source_features": features,
                "trace_id": trace_id
            }
            await self.event_bus.publish(EventType.VALIDATED_FEATURES, validated_features_data)
            log.info(f"Published VALIDATED_FEATURES - Output: {len(validated.features)} validated features")
        except Exception as e:
            log.error(f"Error in handle_features: {e}")
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_features latency: {latency*1000:.2f}ms")

    async def handle_validated_features(self, validated_features_data: dict[str, Any]) -> None:
        trace_id = validated_features_data.get("trace_id", TraceManager.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping signal generation")
                return
            # Extract the ValidatedFeatures object
            validated_features_obj = validated_features_data.get("features")
            if validated_features_obj is None:
                log.warning("No features in validated_features_data")
                return
            # Use ensemble strategy to generate signal from validated features
            # The ensemble strategy internally runs all strategies and combines their signals
            ensemble_signal = await self.ensemble_strategy.generate_signal(validated_features_obj)
            
            # Publish SIGNALS event
            signals_data = {
                "signal": {
                    "signal_type": ensemble_signal.signal_type,
                    "strength": float(ensemble_signal.strength)
                },
                "timestamp": datetime.utcnow(),
                "source_strategy": "ensemble",
                "trace_id": trace_id
            }
            await self.event_bus.publish(EventType.SIGNALS, signals_data)
            log.info(f"Published SIGNALS - Output: ensemble signal {ensemble_signal.signal_type} with strength {ensemble_signal.strength}")
        except Exception as e:
            log.error(f"Error in handle_validated_features: {e}")
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_validated_features latency: {latency*1000:.2f}ms")

    async def handle_signals(self, signals_data: dict[str, Any]) -> None:
        trace_id = signals_data.get("trace_id", TraceManager.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            if await self._is_kill_switch_active():
                log.warning("Kill switch active, skipping signal processing")
                return
            
            # Extract signal from the data
            signal_info = signals_data.get("signal")
            if not signal_info:
                log.warning("No signal in signals data")
                return
            
            symbol = signals_data.get("symbol", "UNKNOWN")
            
            # Convert dict signal to SignalEvent for the allocator
            signal_event = SignalEvent(
                symbol=symbol,
                signal_type=signal_info.get("signal_type", "UNKNOWN"),
                strength=Decimal(str(signal_info.get("strength", 0))),
                timestamp=signals_data.get("timestamp", datetime.utcnow()),
                trace_id=trace_id,
                metadata={}
            )
            
            log.info(f"Processing signal: {signal_event.signal_type} with strength {signal_event.strength}")
            
            # Compute allocation
            allocation_weights = await self.portfolio_allocator.allocate(signal_event)
            if allocation_weights is None:
                log.debug("No allocation computed")
                return
            
            allocation_dict = {k: float(v) for k, v in allocation_weights.weights.items()}
            
            # Run risk check
            risk_metrics = await self.runtime_risk_engine.evaluate_risk(
                allocation_weights=allocation_weights
            )
            # Check risk limits
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
            
            self.last_approved_risk_metrics = risk_metrics
            log.info(f"Risk check passed. VaR={risk_metrics.portfolio_var}, Drawdown={risk_metrics.max_drawdown}, Leverage={risk_metrics.leverage}")
            
            # Publish ORDERS event
            await self.event_bus.publish(EventType.ORDERS, {
                "allocation": allocation_dict,
                "timestamp": datetime.utcnow(),
                "source_ensemble": signal_info,
                "trace_id": trace_id
            })
            log.info(f"Published ORDERS - Output: {len(allocation_dict)} allocations")
        except Exception as e:
            log.error(f"Error in handle_signals: {e}")
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_signals latency: {latency*1000:.2f}ms")

    async def handle_orders(self, orders_data: dict[str, Any]) -> None:
        trace_id = orders_data.get("trace_id", TraceManager.generate())
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
            # Use the last approved risk metrics
            risk_metrics = self.last_approved_risk_metrics
            if risk_metrics is None:
                log.warning("No approved risk metrics available for order")
                return
            # Convert allocation dict to AllocationWeights
            allocation_weights = AllocationWeights(
                timestamp=orders_data.get("timestamp", datetime.utcnow()),
                weights={k: Decimal(str(v)) for k, v in allocation_dict.items()},
                trace_id=trace_id
            )
            # Create and send order via OMS adapter
            order_event = await self.oms_adapter.create_order(
                allocation_weights=allocation_weights,
                risk_metrics=risk_metrics
            )
            log.info(f"Sent order via OMS adapter: {order_event}")
        except Exception as e:
            log.error(f"Error in handle_orders: {e}")
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_orders latency: {latency*1000:.2f}ms")

    async def handle_fills(self, fill_data: dict[str, Any]) -> None:
        trace_id = fill_data.get("trace_id", TraceManager.generate())
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
            
            quantity_dec = Decimal(str(quantity))
            price_dec = Decimal(str(price))
            
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
            
            # Update performance tracking
            if self.state_store:
                await self.state_store.update_performance(symbol, quantity_dec, price_dec)
            
            # Feedback engine processing
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
            log.error(f"Error in handle_fills: {e}")
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_fills latency: {latency*1000:.2f}ms")

    async def handle_risk_alert(self, alert_data: dict[str, Any]) -> None:
        trace_id = alert_data.get("trace_id", TraceManager.generate())
        log = logger.bind(trace_id=trace_id)
        start_time = time.time()
        try:
            log.warning(f"Risk alert received: {alert_data}")
            _ = await self.network_kill_switch.engage_hard_kill(reason="Risk limits exceeded")
        except Exception as e:
            log.error(f"Error in handle_risk_alert: {e}")
        finally:
            latency = time.time() - start_time
            log.debug(f"handle_risk_alert latency: {latency*1000:.2f}ms")

    async def _handle_feedback_update(self, data: dict[str, Any]) -> None:
        """Handle feedback updates from the feedback engine."""
        try:
            logger.debug("Handling feedback update")
            # Update meta-learner with feedback
            # For simplicity, we use a fixed regime; in production, this would come from a regime detector
            regime = "default"
            meta_result = self.meta_learner.update(feedback=data, regime=regime)
            logger.info(f"Updated meta-learner for regime {regime}")
            
            # Use the updated weights to adjust ensemble strategy and allocator
            if meta_result:
                # Update ensemble strategy weights if it supports meta-learning
                if hasattr(self.ensemble_strategy, 'meta_learning_engine') and self.ensemble_strategy.meta_learning_engine:
                    # Convert feedback data to format expected by MetaLearningEngine
                    strategy_scores = data.get('strategy_scores', {})
                    feature_scores = data.get('feature_scores', {})
                    
                    # Prepare strategy_performance dict: strategy_name -> {sharpe, pnl_mean, drawdown, hit_ratio}
                    strategy_performance = {}
                    for strategy_name, score in strategy_scores.items():
                        # Use score as sharpe ratio approximation
                        # Set default values for other metrics (in a real system, these would be computed properly)
                        strategy_performance[strategy_name] = {
                            'sharpe': float(score),
                            'pnl_mean': 0.01,  # Small positive return
                            'drawdown': 0.001, # Small drawdown
                            'hit_ratio': 0.5   # Neutral hit ratio
                        }
                    
                    # Prepare feature_performance dict: feature_name -> (IC, decay)
                    feature_performance = {}
                    for feature_name, ic in feature_scores.items():
                        # Use IC from feedback, set small decay value
                        feature_performance[feature_name] = (float(ic), 0.1)
                    
                    # Update the ensemble strategy's meta-learning engine with converted feedback
                    self.ensemble_strategy.meta_learning_engine.update(
                        strategy_performance=strategy_performance,
                        feature_performance=feature_performance,
                        regime=regime,
                        regime_prob=1.0  # Assume 100% probability for default regime
                    )
                    logger.debug("Updated ensemble strategy's meta-learning engine")
                else:
                    # Fallback: directly set strategy weights if available
                    strategy_weights = meta_result.get('strategy_weights', {})
                    if strategy_weights and hasattr(self.ensemble_strategy, '_strategy_weights'):
                        # Convert strategy name weights to index weights if needed
                        # For simplicity, we assume strategies are in the same order
                        logger.debug(f"Setting ensemble strategy weights: {strategy_weights}")
                        # This would require mapping strategy names to indices
                        # For now, we'll log that we would set weights
                        logger.info(f"Would set ensemble strategy weights: {strategy_weights}")
                
                # Update allocator with risk multiplier if available
                risk_multiplier = meta_result.get('risk_multiplier', 1.0)
                if risk_multiplier != 1.0 and hasattr(self.portfolio_allocator, 'set_risk_multiplier'):
                    self.portfolio_allocator.set_risk_multiplier(risk_multiplier)
                    logger.debug(f"Set allocator risk multiplier to {risk_multiplier}")
                elif risk_multiplier != 1.0:
                    logger.info(f"Would set allocator risk multiplier to {risk_multiplier} (method not available)")
                
                # Update drift detector with new live and historical data
                try:
                    # Access feature data from feedback engine
                    # self.feedback_engine._feature_data: Dict[str, Deque[Tuple[float, float]]]
                    # Each tuple is (feature_value, return)
                    if hasattr(self.feedback_engine, '_feature_data') and self.feedback_engine._feature_data:
                        # Prepare data for drift detection
                        # We'll use the last 100 samples as "live" and the previous 100 as "reference"
                        # If we don't have enough data, we'll use what we have
                        window_size = 100
                        
                        # Initialize dictionaries to hold feature values
                        reference_data = {}  # feature_name -> list of values
                        live_data = {}       # feature_name -> list of values
                        
                        # Process each feature
                        for feature_name, feature_deque in self.feedback_engine._feature_data.items():
                            if len(feature_deque) >= 2:  # Need at least 2 points to split
                                # Extract just the feature values (not the returns)
                                feature_values = [item[0] for item in feature_deque]
                                
                                # Split into reference and live
                                # Reference: older data, Live: more recent data
                                if len(feature_values) >= window_size * 2:
                                    # We have enough data for both windows
                                    reference_vals = feature_values[:-window_size]  # Older data
                                    live_vals = feature_values[-window_size:]       # Recent data
                                elif len(feature_values) >= window_size:
                                    # We have at least one window's worth
                                    # Use first half as reference, second half as live
                                    split_point = len(feature_values) // 2
                                    reference_vals = feature_values[:split_point]
                                    live_vals = feature_values[split_point:split_point + window_size]
                                else:
                                    # Not enough data for meaningful comparison yet
                                    continue
                                
                                # Only proceed if we have data in both windows
                                if len(reference_vals) > 0 and len(live_vals) > 0:
                                    reference_data[feature_name] = reference_vals
                                    live_data[feature_name] = live_vals
                        
                        # If we have data to compare, run drift detection
                        if reference_data and live_data:
                            # Convert to polars DataFrames
                            # We need to handle different lengths by padding or truncating
                            # For simplicity, we'll create DataFrames with the same number of rows
                            # by taking the minimum length for each feature
                            
                            # Find the minimum length across all features for reference and live
                            min_ref_len = min(len(vals) for vals in reference_data.values()) if reference_data else 0
                            min_live_len = min(len(vals) for vals in live_data.values()) if live_data else 0
                            
                            if min_ref_len > 0 and min_live_len > 0:
                                # Truncate to minimum length
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
                
                # Log to MLflow periodically (every 10 updates)
                if self.mlflow_manager and self.mlflow_manager.is_enabled():
                    self._feedback_update_count += 1
                    if self._feedback_update_count % 10 == 0:
                        try:
                            # Extract strategy name from feedback data if available
                            strategy_name = data.get('strategy_name', 'unknown')
                            # Prepare parameters, metrics, and artifacts for MLflow
                            parameters = {
                                "strategy_name": strategy_name,
                                "regime": regime,
                                "feedback_timestamp": datetime.utcnow().isoformat(),
                            }
                            # Flatten any nested dictionaries in data for parameters (up to one level)
                            for key, value in data.items():
                                if isinstance(value, (str, int, float, bool)) and key not in ['strategy_name', 'regime']:
                                    parameters[key] = value
                                elif isinstance(value, dict):
                                    # For dict values, we log them as JSON string in artifacts later
                                    pass
                            metrics = {}
                            # Extract known metrics if present
                            for metric_key in ['sharpe', 'drawdown', 'hit_rate', 'pnl']:
                                if metric_key in data:
                                    metrics[metric_key] = float(data[metric_key])
                            # If we don't have specific metrics, we can log a placeholder
                            if not metrics:
                                metrics['feedback_value'] = 1.0  # Placeholder
                            
                            # Prepare artifacts: we'll log the feedback data as a JSON artifact
                            artifacts = {
                                "feedback_data": data
                            }
                            
                            # Log the run asynchronously (fire and forget)
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
        
        # Simple average of strengths
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

    async def run(self) -> None:
        logger.info("Starting TradingOrchestrator event loop")
        # Start the event bus
        await self.event_bus.start()
        # Start background components
        await self._start_components()
        
        # Non-blocking wait until stop is signal/requested
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()
