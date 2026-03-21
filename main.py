#!/usr/bin/env python3
"""Main entry point for the QTrader live trading system."""

import asyncio
import signal
import sys
from decimal import Decimal
from datetime import datetime

from qtrader.core.event_bus import EventBus
from qtrader.core.logger import StructuredLogger
from qtrader.core.types import MarketData, EventType, AlphaOutput
from qtrader.strategy.alpha.alpha_base import AlphaBase
from qtrader.strategy.validation.feature_validator import SimpleFeatureValidator
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.portfolio.allocator import SimpleAllocator
from qtrader.risk.runtime import RuntimeRiskEngine
from qtrader.execution.oms_adapter import SimpleOMSAdapter
from qtrader.output.execution.oms import UnifiedOMS  # Import the real UnifiedOMS


class ExampleAlpha(AlphaBase):
    """Example alpha generator for demonstration."""
    
    def __init__(self):
        super().__init__("example_alpha")
    
    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """Generate a simple example alpha."""
        # In reality, this would calculate actual alpha factors
        # For demo, we'll return a simple moving average crossover signal
        alpha_value = Decimal('0.05')  # Placeholder alpha value
        
        return AlphaOutput(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            alpha_values={"example_alpha": alpha_value},
            metadata={"alpha_type": "example"}
        )


async def main():
    """Main function to run the QTrader system."""
    # Setup logging
    logger = StructuredLogger("qtrader_main")
    logger.info("Starting QTrader system")
    
    # Setup event bus
    event_bus = EventBus(logger=logger)
    
    # Create components
    alpha_generator = ExampleAlpha()
    feature_validator = SimpleFeatureValidator()
    
    # Create strategies
    probabilistic_strategy = ProbabilisticStrategy(
        symbol="AAPL",
        capital=Decimal('100000')
    )
    
    ensemble_strategy = EnsembleStrategy(
        strategies=[probabilistic_strategy],
        performance_window=20
    )
    
    # Use ensemble strategy
    strategy = ensemble_strategy
    
    allocator = SimpleAllocator()
    
    # Create mock OMS and risk engine
    oms = UnifiedOMS()  # Use the imported UnifiedOMS
    risk_engine = RuntimeRiskEngine(oms=oms)
    oms_adapter = SimpleOMSAdapter()
    
    # Create orchestrator (no config needed anymore)
    orchestrator = QTraderEngine(
        event_bus=event_bus,
        logger=logger,
        alpha_generator=alpha_generator,
        feature_validator=feature_validator,
        strategy=strategy,
        allocator=allocator,
        risk_engine=risk_engine,
        oms_adapter=oms_adapter
    )
    
    # Setup signal handling for graceful shutdown
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(orchestrator.stop())
    
    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Start the orchestrator
        await orchestrator.start()
        
        # Keep the system running
        logger.info("QTrader system is running. Press Ctrl+C to stop.")
        while orchestrator._running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        # Ensure cleanup
        await orchestrator.stop()
        logger.info("QTrader system stopped")


# Import QTraderEngine after defining dependencies to avoid circular imports
from qtrader.core.orchestrator import QTraderEngine


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)