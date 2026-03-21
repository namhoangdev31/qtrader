"""Orchestrator for the QTrader live trading system.

This module coordinates the event-driven pipeline: market data -> alpha generation ->
feature validation -> strategy -> risk -> execution.
"""

import asyncio
from typing import Dict, Any
from decimal import Decimal

from qtrader.core.event import (
    MarketDataEvent,
    FeatureEvent,
    SignalEvent as CoreSignalEvent,
    OrderEvent as CoreOrderEvent,
    FillEvent,
    RiskEvent,
    SystemEvent,
    EventType
)
from qtrader.core.types import LoggerProtocol, EventBusProtocol
from qtrader.strategy.alpha.alpha_base import AlphaBase
from ..strategy.validation.feature_validator import FeatureValidator
from ..strategy.probabilistic_strategy import ProbabilisticStrategy
from ..strategy.ensemble_strategy import EnsembleStrategy
from ..portfolio.allocator import AllocatorBase
from ..risk.runtime import RuntimeRiskEngine
from ..execution.oms_adapter import OMSAdapter


class QTraderEngine:
    """Main orchestrator for the QTrader trading system."""

    def __init__(
        self,
        event_bus: EventBusProtocol,
        logger: LoggerProtocol,
        alpha_generator: AlphaBase,
        feature_validator: FeatureValidator,
        strategy: ProbabilisticStrategy | EnsembleStrategy,
        allocator: AllocatorBase,
        risk_engine: RuntimeRiskEngine,
        oms_adapter: OMSAdapter,
    ):
        self.event_bus = event_bus
        self.logger = logger
        self.alpha_generator = alpha_generator
        self.feature_validator = feature_validator
        self.strategy = strategy
        self.allocator = allocator
        self.risk_engine = risk_engine
        self.oms_adapter = oms_adapter
        self._running = False
        # Store latest market data for risk calculations
        self._latest_market_data: MarketDataEvent = None

    async def start(self) -> None:
        """Start the trading orchestrator."""
        self.logger.info("Starting QTrader orchestrator")
        self._running = True
        # Subscribe to market data events
        self.event_bus.subscribe(EventType.MARKET_DATA, self._on_market_data)
        # Start the event bus if not already started
        await self.event_bus.start()

    async def stop(self) -> None:
        """Stop the trading orchestrator."""
        self.logger.info("Stopping QTrader orchestrator")
        self._running = False
        self.event_bus.unsubscribe(EventType.MARKET_DATA, self._on_market_data)
        await self.event_bus.stop()

    async def _on_market_data(self, market_data_event: MarketDataEvent) -> None:
        """Process incoming market data event."""
        if not self._running:
            return

        try:
            # Store latest market data for risk calculations
            self._latest_market_data = market_data_event

            # Generate alpha
            feature_event: FeatureEvent = await self.alpha_generator.generate(
                market_data_event
            )
            
            # Validate features
            validated_feature_event: FeatureEvent = await self.feature_validator.validate(
                feature_event
            )
            
            # Generate trading signal
            signal_event: CoreSignalEvent = await self.strategy.generate_signal(
                validated_feature_event
            )
            
            # Calculate portfolio allocation
            # Assume allocator.allocate returns a dict of symbol -> weight
            allocation_dict: Dict[str, float] = await self.allocator.allocate(
                signal_event
            )
            
            # Risk check
            # We need to evaluate risk based on allocation and current market data
            # For simplicity, we pass the latest market data to the risk engine's compute method
            # and ask for a risk metric like 'exposure' or 'var'. But we want a RiskMetrics object.
            # We'll adjust the risk engine to have a method that takes allocation and returns RiskMetrics.
            # Since we don't have that, we'll create a simple RiskMetrics object here.
            # In a production system, the risk engine would have such a method.
            risk_metrics = self._create_risk_metrics(
                allocation_dict, 
                market_data_event.timestamp
            )
            
            # Generate orders
            order_event: CoreOrderEvent = await self.oms_adapter.create_order(
                allocation_dict, risk_metrics
            )
            
            # Publish order event
            await self.event_bus.publish(EventType.ORDER, order_event)
            
        except Exception as e:
            self.logger.error(
                f"Error in orchestrator pipeline: {e}",
                exc_info=True,
            )
            # Publish system error event
            await self.event_bus.publish(
                EventType.SYSTEM,
                SystemEvent(
                    action="ERROR",
                    reason=str(e),
                    metadata={
                        "component": "orchestrator",
                        "timestamp": market_data_event.timestamp.isoformat(),
                    },
                )
            )

    def _create_risk_metrics(
        self, 
        allocation_dict: Dict[str, float], 
        timestamp: datetime
    ) -> Dict[str, Any]:
        """Create risk metrics from allocation dict (simplified for now)."""
        # In a real implementation, we would use the risk engine to calculate
        # proper risk metrics based on the allocation and current positions.
        # For now, we return dummy values.
        total_allocation = sum(allocation_dict.values())
        return {
            "portfolio_var": Decimal('0.01'),  # 1% VaR
            "portfolio_volatility": Decimal('0.05'),  # 5% volatility
            "max_drawdown": Decimal('0.02'),  # 2% drawdown
            "leverage": Decimal(str(min(total_allocation, 2.0))),  # simple leverage approximation
            "timestamp": timestamp,
        }