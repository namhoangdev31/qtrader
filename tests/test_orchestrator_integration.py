#!/usr/bin/env python3
"""Test script for orchestrator integration with new components."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from unittest.mock import Mock, AsyncMock
from decimal import Decimal
from datetime import datetime

from qtrader.core.event_bus import EventBus
from qtrader.core.types import LoggerProtocol
from qtrader.core.logger import StructuredLogger
from qtrader.core.types import MarketData, EventType
from qtrader.core.orchestrator import TradingOrchestrator
from qtrader.strategy.alpha.alpha_base import AlphaBase
from qtrader.strategy.validation.feature_validator import FeatureValidator
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.portfolio.allocator import AllocatorBase
from qtrader.risk.runtime import RuntimeRiskEngine
from qtrader.execution.oms_adapter import OMSAdapter
from qtrader.feedback.feedback_engine import FeedbackEngine

# Mock logger adapter
class SimpleLoggerAdapter:
    def __init__(self, logger):
        self.logger = logger
    
    def info(self, message: str, **kwargs) -> None:
        self.logger.info(message)
    
    def warning(self, message: str, **kwargs) -> None:
        self.logger.warning(message)
    
    def error(self, message: str, **kwargs) -> None:
        self.logger.error(message)
    
    def debug(self, message: str, **kwargs) -> None:
        self.logger.debug(message)
    
    def critical(self, message: str, **kwargs) -> None:
        self.logger.critical(message)

# Mock components
class MockAlpha(AlphaBase):
    def __init__(self, name: str):
        super().__init__(name)
    
    async def generate(self, market_data: MarketData):
        from qtrader.core.types import AlphaOutput
        return AlphaOutput(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            alpha_values={"test_alpha": Decimal('0.5')}
        )

class MockFeatureValidator(FeatureValidator):
    async def validate(self, alpha_output):
        from qtrader.core.types import ValidatedFeatures
        return ValidatedFeatures(
            symbol=alpha_output.symbol,
            timestamp=alpha_output.timestamp,
            features=alpha_output.alpha_values,
            validation_metadata={}
        )

class MockStrategy(ProbabilisticStrategy):
    def __init__(self):
        super().__init__(symbol="TEST", capital=Decimal('10000'))
    
    async def generate_signal(self, validated_features):
        from qtrader.core.types import SignalEvent
        # Return a simple signal
        return SignalEvent(
            symbol="TEST",
            signal_type="LONG",
            strength=Decimal('0.8'),
            timestamp=datetime.utcnow(),
            metadata={}
        )

class MockAllocator(AllocatorBase):
    async def allocate(self, signal_event):
        from qtrader.core.types import AllocationWeights
        return AllocationWeights(
            timestamp=signal_event.timestamp,
            weights={"TEST": Decimal('1.0')}
        )

class MockRiskEngine:
    async def evaluate_risk(self, allocation_weights):
        from qtrader.core.types import RiskMetrics
        return RiskMetrics(
            timestamp=datetime.now(),
            portfolio_var=Decimal('0.01'),
            portfolio_volatility=Decimal('0.1'),
            max_drawdown=Decimal('0.05'),
            leverage=Decimal('1.0')
        )

class MockOMSAdapter(OMSAdapter):
    async def create_order(self, allocation_weights, risk_metrics):
        from qtrader.core.types import OrderEvent
        return OrderEvent(
            order_id="test_order",
            symbol="TEST",
            timestamp=datetime.now(),
            order_type="MARKET",
            side="BUY",
            quantity=Decimal('100'),
            price=Decimal('100.0')
        )
    
    async def cancel_all_orders(self):
        # Mock implementation
        pass

async def test_orchestrator_integration():
    """Test that the orchestrator initializes with all new components."""
    print("Testing orchestrator integration...")
    
    # Setup logging
    logger = StructuredLogger("test_orchestrator")
    
    # Create event bus
    event_bus = EventBus(logger=SimpleLoggerAdapter(logger))
    
    # Create mock components
    alpha_modules = [MockAlpha("test_alpha")]
    feature_validator = MockFeatureValidator()
    strategies = [MockStrategy()]
    ensemble_strategy = EnsembleStrategy(strategies=strategies, performance_window=20)
    portfolio_allocator = MockAllocator()
    risk_engine = MockRiskEngine()
    oms_adapter = MockOMSAdapter()
    
    # Create orchestrator
    orchestrator = TradingOrchestrator(
        event_bus=event_bus,
        market_data_adapter=None,
        alpha_modules=alpha_modules,
        feature_validator=feature_validator,
        strategies=strategies,
        ensemble_strategy=ensemble_strategy,
        portfolio_allocator=portfolio_allocator,
        runtime_risk_engine=risk_engine,
        oms_adapter=oms_adapter
    )
    
    # Verify components are initialized
    assert hasattr(orchestrator, 'meta_learner'), "MetaLearner not initialized"
    assert hasattr(orchestrator, 'drift_detector'), "DriftDetector not initialized"
    assert hasattr(orchestrator, 'shadow_engine'), "ShadowEngine not initialized"
    assert hasattr(orchestrator, 'resource_monitor'), "ResourceMonitor not initialized"
    assert hasattr(orchestrator, 'network_kill_switch'), "NetworkKillSwitch not initialized"
    assert hasattr(orchestrator, 'feedback_engine'), "FeedbackEngine not initialized"
    
    print("✓ All components initialized successfully")
    
    # Test that we can start the orchestrator (without actually running the loop)
    await event_bus.start()
    await orchestrator._start_components()
    
    print("✓ Orchestrator components started successfully")
    
    # Cleanup
    await orchestrator._stop_components()
    await event_bus.stop()
    
    print("✓ Orchestrator integration test passed!")

if __name__ == "__main__":
    asyncio.run(test_orchestrator_integration())