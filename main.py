#!/usr/bin/env python3
"""Main entry point for the QTrader live trading system."""

import asyncio
import signal
import sys
from decimal import Decimal
from datetime import datetime

from loguru import logger

from qtrader.core.event_bus import EventBus
from qtrader.core.events import MarketEvent, MarketPayload, EventType
from qtrader.core.types import MarketData, AlphaOutput
from qtrader.strategy.alpha.alpha_base import AlphaBase
from qtrader.strategy.validation.feature_validator import SimpleFeatureValidator
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from qtrader.portfolio.allocator import SimpleAllocator
from qtrader.risk.runtime import RuntimeRiskEngine
from qtrader.oms.oms_adapter import OMSAdapter
from qtrader.execution.execution_engine import SimulatedExchangeAdapter
from qtrader.core.orchestrator import TradingOrchestrator


class ExampleAlpha(AlphaBase):
    """Example alpha generator for demonstration."""

    def __init__(self) -> None:
        super().__init__("example_alpha")

    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """Generate a simple example alpha."""
        alpha_value = Decimal("0.05")

        return AlphaOutput(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            alpha_values={"example_alpha": alpha_value},
            metadata={"alpha_type": "example"},
        )


async def main() -> None:
    """Main function to run the QTrader system."""
    logger.info("Starting QTrader system")

    # Setup event bus
    event_bus = EventBus()

    # Create components
    alpha_module = ExampleAlpha()
    feature_validator = SimpleFeatureValidator()

    # Create strategies
    probabilistic_strategy = ProbabilisticStrategy(
        symbol="AAPL",
        capital=Decimal("100000"),
    )

    ensemble_strategy = EnsembleStrategy(
        strategies=[probabilistic_strategy],
        performance_window=20,
    )

    allocator = SimpleAllocator()

    # Create OMS adapter
    oms_adapter = OMSAdapter()

    # Create risk engine
    risk_engine = RuntimeRiskEngine()

    # Create a simulated exchange adapter for testing
    simulated_adapter = SimulatedExchangeAdapter(name="SimulatedExchange")
    simulated_adapter.set_price("AAPL", Decimal("150.0"))

    # Create orchestrator
    orchestrator = TradingOrchestrator(
        event_bus=event_bus,
        market_data_adapter=None,
        alpha_modules=[alpha_module],
        feature_validator=feature_validator,
        strategies=[probabilistic_strategy],
        ensemble_strategy=ensemble_strategy,
        portfolio_allocator=allocator,
        runtime_risk_engine=risk_engine,
        oms_adapter=oms_adapter,
    )

    # Setup signal handling for graceful shutdown
    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(orchestrator.halt_core("SHUTDOWN_SIGNAL"))

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass  # Windows doesn't support add_signal_handler

    try:
        # Initialize and start the orchestrator
        orchestrator.initialize()
        await orchestrator.run()

    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        logger.info("QTrader system stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
