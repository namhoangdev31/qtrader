"""Orchestrator for the QTrader live trading system.

This module coordinates the event-driven pipeline: market data -> alpha generation ->
feature validation -> strategy -> risk -> execution.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal

from qtrader.core.types import (
    EventType,
    LoggerProtocol,
    EventBusProtocol,
    MarketData,
    AllocationWeights,
    RiskMetrics,
    ValidatedFeatures,
    SignalEvent,
)
from qtrader.core.state_store import StateStore, Position
from qtrader.strategy.alpha.alpha_base import AlphaBase
from qtrader.strategy.validation.feature_validator import FeatureValidator
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.portfolio.allocator import AllocatorBase
from qtrader.risk.runtime import RuntimeRiskEngine
from qtrader.execution.oms_adapter import OMSAdapter

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """Main orchestrator for the QTrader trading system."""

    def __init__(
        self,
        event_bus: EventBusProtocol,
        market_data_adapter: object,  # Not used in handlers but kept for interface compatibility
        alpha_modules: List[AlphaBase],
        feature_validator: FeatureValidator,
        strategies: List[ProbabilisticStrategy],
        ensemble_strategy: EnsembleStrategy,
        portfolio_allocator: AllocatorBase,
        runtime_risk_engine: RuntimeRiskEngine,
        oms_adapter: OMSAdapter,
        state_store: Optional[StateStore] = None,
    ):
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

        # State limits (example values - should be configurable via constructor or config)
        self.max_drawdown = Decimal('0.20')  # 20%
        self.max_var = Decimal('0.05')       # 5% VaR
        self.max_leverage = Decimal('5.0')   # 5x leverage

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        self.event_bus.subscribe(EventType.MARKET_DATA, self.handle_market_data)
        self.event_bus.subscribe(EventType.FEATURES, self.handle_features)
        self.event_bus.subscribe(EventType.VALIDATED_FEATURES, self.handle_validated_features)
        self.event_bus.subscribe(EventType.SIGNALS, self.handle_signals)
        self.event_bus.subscribe(EventType.ORDERS, self.handle_orders)
        self.event_bus.subscribe(EventType.FILLS, self.handle_fills)
        self.event_bus.subscribe(EventType.RISK_ALERT, self.handle_risk_alert)

    async def handle_market_data(self, market_data: MarketData):
        start_time = time.time()
        try:
            logger.info(f"Handling market data for {market_data.symbol} - Input: close={market_data.close}, volume={market_data.volume}")
            # Compute alpha features from all modules
            features = {}
            for alpha in self.alpha_modules:
                # Assuming alpha.generate returns an AlphaOutput
                alpha_output = await alpha.generate(market_data)
                if hasattr(alpha_output, 'alpha_values') and isinstance(alpha_output.alpha_values, dict):
                    features.update(alpha_output.alpha_values)
                else:
                    logger.warning(f"Alpha module {alpha.name} returned unexpected output: {type(alpha_output)}")
            
            # Publish FEATURES event with symbol tracking
            features_data = {
                "features": features,
                "timestamp": datetime.utcnow(),
                "source_market_data": market_data,
                "symbol": market_data.symbol
            }
            await self.event_bus.publish(EventType.FEATURES, features_data)
            logger.info(f"Published FEATURES for {market_data.symbol} - Output: {len(features)} features computed")
        except Exception as e:
            logger.error(f"Error in handle_market_data for {getattr(market_data, 'symbol', 'UNKNOWN')}: {e}", exc_info=True)
            # Fallback: do not publish features
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_market_data latency: {latency*1000:.2f}ms")

    async def handle_features(self, features_data: Dict[str, Any]):
        start_time = time.time()
        try:
            symbol = features_data.get("symbol", "UNKNOWN")
            if await self._is_kill_switch_active():
                logger.warning(f"Kill switch active, skipping feature validation for {symbol}")
                return
            logger.debug(f"Handling features for {symbol} - Input: {len(features_data.get('features', {}))} features")
            features = features_data.get("features", {})
            # Validate features
            validated = await self.feature_validator.validate(features)
            if validated is None:
                logger.warning(f"Feature validation failed for {symbol}")
                return
            # Publish VALIDATED_FEATURES event
            validated_features_data = {
                "features": validated,
                "timestamp": datetime.utcnow(),
                "source_features": features,
                "symbol": symbol
            }
            await self.event_bus.publish(EventType.VALIDATED_FEATURES, validated_features_data)
            logger.info(f"Published VALIDATED_FEATURES for {symbol} - Output: {len(validated.features)} validated features")
        except Exception as e:
            logger.error(f"Error in handle_features for {features_data.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_features latency: {latency*1000:.2f}ms")

    async def handle_validated_features(self, validated_features_data: Dict[str, Any]):
        start_time = time.time()
        try:
            symbol = validated_features_data.get("symbol", "UNKNOWN")
            if await self._is_kill_switch_active():
                logger.warning(f"Kill switch active, skipping signal generation for {symbol}")
                return
            logger.debug(f"Handling validated features for {symbol} - Input: {len(validated_features_data.get('features', {}).features) if hasattr(validated_features_data.get('features'), 'features') else 0} validated features")
            # Extract the ValidatedFeatures object
            validated_features_obj = validated_features_data.get("features")
            if validated_features_obj is None:
                logger.warning(f"No features in validated_features_data for {symbol}")
                return
            if not isinstance(validated_features_obj, ValidatedFeatures):
                logger.warning(f"Features is not a ValidatedFeatures object for {symbol}")
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
                "symbol": symbol
            }
            await self.event_bus.publish(EventType.SIGNALS, signals_data)
            logger.info(f"Published SIGNALS for {symbol} - Output: ensemble signal {ensemble_signal.signal_type} with strength {ensemble_signal.strength}")
        except Exception as e:
            logger.error(f"Error in handle_validated_features for {validated_features_data.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_validated_features latency: {latency*1000:.2f}ms")

    async def handle_signals(self, signals_data: Dict[str, Any]):
        start_time = time.time()
        try:
            symbol = signals_data.get("symbol", "UNKNOWN")
            if await self._is_kill_switch_active():
                logger.warning(f"Kill switch active, skipping signal processing for {symbol}")
                return
            logger.debug(f"Handling signals for {symbol} - Input: signal={signals_data.get('signal')}")
            
            # Extract signal from the data (published by handle_validated_features)
            signal_info = signals_data.get("signal")
            if not signal_info:
                logger.warning(f"No signal in signals data for {symbol}")
                return
            
            # Convert dict signal to SignalEvent for the allocator
            signal_event = SignalEvent(
                symbol=symbol,
                signal_type=signal_info.get("signal_type", "UNKNOWN"),
                strength=Decimal(str(signal_info.get("strength", 0))),
                timestamp=signals_data.get("timestamp", datetime.utcnow()),
                metadata={}
            )
            
            logger.info(f"Processing signal for {symbol}: {signal_event.signal_type} with strength {signal_event.strength}")
            
            # Compute allocation using the allocator
            allocation_weights = await self.portfolio_allocator.allocate(signal_event)
            if allocation_weights is None:
                logger.debug(f"No allocation computed for {symbol}")
                return
            
            # Convert allocation_weights to dict for risk checking and storage
            allocation_dict = {k: float(v) for k, v in allocation_weights.weights.items()}
            
            logger.info(f"Allocation computed for {symbol}: {allocation_dict}")
            
            # Run risk check
            risk_metrics = await self.runtime_risk_engine.evaluate_risk(
                allocation_weights=allocation_weights
            )
            # Check risk limits
            if (risk_metrics.portfolio_var > self.max_var or 
                risk_metrics.max_drawdown > self.max_drawdown or 
                risk_metrics.leverage > self.max_leverage):
                logger.warning(f"Risk check failed for {symbol}, blocking order. Reason: VaR={risk_metrics.portfolio_var} > {self.max_var} or Drawdown={risk_metrics.max_drawdown} > {self.max_drawdown} or Leverage={risk_metrics.leverage} > {self.max_leverage}")
                await self.event_bus.publish(EventType.RISK_ALERT, {
                    "allocation": allocation_dict,
                    "risk_metrics": risk_metrics,
                    "timestamp": datetime.utcnow(),
                    "reason": "Risk limits exceeded"
                })
                return
            # Store approved allocation and risk metrics for handle_orders
            self.last_approved_allocation = allocation_dict
            self.last_approved_risk_metrics = risk_metrics
            logger.info(f"Risk check passed for {symbol}. VaR={risk_metrics.portfolio_var}, Drawdown={risk_metrics.max_drawdown}, Leverage={risk_metrics.leverage}")
            # Publish ORDERS event
            await self.event_bus.publish(EventType.ORDERS, {
                "allocation": allocation_dict,
                "timestamp": datetime.utcnow(),
                "source_ensemble": signal_info,
                "symbol": symbol  # Include symbol for completeness
            })
            logger.info(f"Published ORDERS for {symbol} - Output: {len(allocation_dict)} allocations")
        except Exception as e:
            logger.error(f"Error in handle_signals for {signals_data.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_signals latency: {latency*1000:.2f}ms")

    async def handle_orders(self, orders_data: Dict[str, Any]):
        start_time = time.time()
        try:
            symbol = orders_data.get("symbol", "UNKNOWN")
            if await self._is_kill_switch_active():
                logger.warning(f"Kill switch active, skipping order submission for {symbol}")
                return
            logger.debug(f"Handling orders for {symbol} - Input: {len(orders_data.get('allocation', {}))} allocations")
            allocation_dict = orders_data.get("allocation", {})
            if not allocation_dict:
                logger.warning(f"No allocation in orders data for {symbol}")
                return
            # Use the last approved risk metrics (should match this allocation)
            risk_metrics = self.last_approved_risk_metrics
            if risk_metrics is None:
                logger.warning(f"No approved risk metrics available for order for {symbol}")
                # As a fallback, we could recompute, but that might be inconsistent
                # For safety, we'll skip sending the order
                return
            # Convert allocation dict to AllocationWeights
            allocation_weights = AllocationWeights(
                timestamp=orders_data.get("timestamp", datetime.utcnow()),
                weights={k: Decimal(str(v)) for k, v in allocation_dict.items()}
            )
            # Create and send order via OMS adapter
            order_event = await self.oms_adapter.create_order(
                allocation_weights=allocation_weights,
                risk_metrics=risk_metrics
            )
            logger.info(f"Sent order via OMS adapter for {symbol}: {order_event}")
            # In a real system, the OMSAdapter.create_order might actually send the order
            # or return an order event that needs to be sent elsewhere.
            # Based on the requirement "send to OMS", we'll assume create_order handles the sending.
        except Exception as e:
            logger.error(f"Error in handle_orders for {orders_data.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_orders latency: {latency*1000:.2f}ms")

    async def handle_fills(self, fill_data: Dict[str, Any]):
        start_time = time.time()
        try:
            logger.debug(f"Handling fills - Input: symbol={fill_data.get('symbol')}, quantity={fill_data.get('quantity')}, price={fill_data.get('price')}")
            symbol = fill_data.get("symbol")
            quantity = fill_data.get("quantity")
            price = fill_data.get("price")
            if symbol is None or quantity is None or price is None:
                logger.warning("Invalid fill data")
                return
            # Convert to Decimal for consistency with Position
            quantity_dec = Decimal(str(quantity))
            price_dec = Decimal(str(price))
            # Update positions via state store
            current_position = await self.state_store.get_position(symbol)
            if current_position:
                # Update existing position
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
                # Create new position
                new_position = Position(
                    symbol=symbol,
                    quantity=quantity_dec,
                    average_price=price_dec
                )
                await self.state_store.set_position(new_position)
            
            # Update performance tracking (keeping this in orchestrator for now)
            # In a more complete implementation, this could also move to state store
            # but we'll keep it simple for now
            # TODO: Consider moving performance tracking to state store
            # For now, we'll keep it local as it's primarily used for logging
            if not hasattr(self, '_local_performance_tracker'):
                self._local_performance_tracker = {}
            if symbol not in self._local_performance_tracker:
                self._local_performance_tracker[symbol] = {"total_quantity": 0, "total_cost": 0.0}
            tracker = self._local_performance_tracker[symbol]
            tracker["total_quantity"] += quantity_dec
            tracker["total_cost"] += quantity_dec * price_dec
            avg_price = tracker["total_cost"] / tracker["total_quantity"] if tracker["total_quantity"] != 0 else 0
            logger.info(f"Updated position for {symbol}: {self._local_performance_tracker[symbol]['total_quantity']} (avg price: {avg_price:.2f})")
        except Exception as e:
            logger.error(f"Error in handle_fills: {e}", exc_info=True)
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_fills latency: {latency*1000:.2f}ms")

    async def handle_risk_alert(self, alert_data: Dict[str, Any]):
        start_time = time.time()
        try:
            logger.warning(f"Risk alert received: {alert_data}")
            # Activate kill switch via state store or local flag
            # For now, we'll keep the kill switch local as it's used for immediate checks
            # TODO: Consider moving kill switch state to state store for system-wide consistency
            self.kill_switch_active = True
            # Cancel all orders
            # Note: OMSAdapter from the base class doesn't have cancel_all_orders
            # This would need to be implemented in a concrete subclass or handled differently
            logger.warning("Kill switch activated - OMSAdapter does not support cancel_all_orders in base class")
            # In a real implementation, we would call a method on the OMS adapter to cancel orders
        except Exception as e:
            logger.error(f"Error in handle_risk_alert: {e}", exc_info=True)
        finally:
            latency = time.time() - start_time
            logger.debug(f"handle_risk_alert latency: {latency*1000:.2f}ms")

    async def _is_kill_switch_active(self) -> bool:
        """Check if kill switch is active."""
        # For now, we keep this locally for immediate response
        # TODO: Consider moving to state store for system-wide consistency
        return self.kill_switch_active

    def _simple_ensemble_combine(self, signals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Simple ensemble combination when the ensemble strategy doesn't support direct signal combination."""
        if not signals:
            return None
        
        # Simple average of strengths
        total_strength = 0.0
        count = 0
        for signal_name, signal_data in signals.items():
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

    def _get_signal_reason(self, signal: Dict[str, Any]) -> str:
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

    async def run(self):
        logger.info("Starting TradingOrchestrator event loop")
        # Start the event bus
        await self.event_bus.start()
        # Keep the orchestrator running
        while True:
            try:
                await asyncio.sleep(0.01)  # Reduced CPU usage while still responsive
            except Exception as e:
                logger.error(f"Error in event loop: {e}", exc_info=True)