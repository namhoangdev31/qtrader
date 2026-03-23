#!/usr/bin/env python3
"""Quick integration test for the new components."""
from unittest.mock import MagicMock

from qtrader.core.orchestrator import TradingOrchestrator
from qtrader.core.state_store import StateStore

def test_orchestrator_instantiation():
    """Test that the orchestrator can be instantiated with the new components."""
    # Create mocks for required dependencies
    event_bus = MagicMock()
    market_data_adapter = MagicMock()
    alpha_modules = []
    feature_validator = MagicMock()
    strategies = []
    ensemble_strategy = MagicMock()
    portfolio_allocator = MagicMock()
    runtime_risk_engine = MagicMock()
    oms_adapter = MagicMock()
    state_store = StateStore()
    
    # Create the orchestrator
    orchestrator = TradingOrchestrator(
        event_bus=event_bus,
        market_data_adapter=market_data_adapter,
        alpha_modules=alpha_modules,
        feature_validator=feature_validator,
        strategies=strategies,
        ensemble_strategy=ensemble_strategy,
        portfolio_allocator=portfolio_allocator,
        runtime_risk_engine=runtime_risk_engine,
        oms_adapter=oms_adapter,
        state_store=state_store
    )
    
    # Verify that the feedback engine was created
    assert hasattr(orchestrator, 'feedback_engine')
    assert orchestrator.feedback_engine is not None
    
    print("Integration test passed: Orchestrator instantiated successfully with feedback engine")

if __name__ == "__main__":
    test_orchestrator_instantiation()