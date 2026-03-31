"""Canonical Sovereign Runner for QTrader.

This script is the single authoritative entry point for starting a live trading 
instance. It initializes the Unified Trading Orchestrator and manages the 
process lifecycle.
"""

import asyncio
import signal
import sys
import argparse
from pathlib import Path
from loguru import logger

from qtrader.core.orchestrator import TradingOrchestrator, SystemState
from qtrader.core.bus import EventBus
from qtrader.core.config_manager import ConfigManager

# Internal component factory (Mocked for this implementation)
# In production, these are loaded dynamically based on config
def bootstrap_components(config_path: str):
    logger.info(f"BOOTSTRAP | Loading components from {config_path}")
    return {
        "event_bus": EventBus(),
        "market_data_adapter": object(),
        "alpha_modules": [],
        "feature_validator": None,
        "strategies": [],
        "ensemble_strategy": None,
        "portfolio_allocator": None,
        "runtime_risk_engine": None,
        "oms_adapter": None,
    }

async def main():
    parser = argparse.ArgumentParser(description="QTrader Sovereign Runner")
    parser.add_argument("config", type=str, help="Path to bot configuration YAML")
    args = parser.parse_args()

    # 1. Component Bootstrap
    components = bootstrap_components(args.config)
    
    # 2. Orchestrator Initialization
    orchestrator = TradingOrchestrator(**components)
    
    # 3. Signal Handling
    loop = asyncio.get_event_loop()
    
    def handle_exit():
        logger.warning("RUNNER_LIFECYCLE | Exit signal received. Initiating halt...")
        asyncio.create_task(orchestrator.halt_core("SIGINT_SIGTERM"))
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_exit)

    # 4. Sovereign Execution
    try:
        logger.info("RUNNER_LIFECYCLE | Starting Sovereign Orchestrator...")
        await orchestrator.run()
    except Exception as e:
        logger.critical(f"RUNNER_FATAL | Unhandled exception in lifecycle: {e}")
        sys.exit(1)
    finally:
        logger.info("RUNNER_LIFECYCLE | Sovereign Runner terminated.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
