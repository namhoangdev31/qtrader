"""
Execution Service.
Dedicated process for Order Management and Exchange Connectivity.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from qtrader.execution.oms_adapter import ExecutionOMSAdapter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ExecutionService")

class ExecutionService:
    def __init__(self) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)
        
        # In a real deployment, exchange adapters would be loaded from config
        self.oms_adapter = ExecutionOMSAdapter(exchange_adapters={})

    def handle_exit(self, *args: Any) -> None:
        logger.info("Shutdown signal received")
        self.running = False

    async def main_loop(self) -> None:
        logger.info("Starting Execution Service...")
        await self.oms_adapter.start()
        
        while self.running:
            # This service would typically listen to a message bus (Redis/NATS)
            # For now, we simulate a heartbeat connectivity check
            logger.debug("Execution Service Heartbeat - Connected to 0 exchanges")
            await asyncio.sleep(10)

    async def run(self) -> None:
        try:
            await self.main_loop()
        finally:
            await self.oms_adapter.stop()

if __name__ == "__main__":
    service = ExecutionService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal execution service crash: {e}")
        sys.exit(1)
