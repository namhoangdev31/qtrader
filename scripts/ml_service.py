"""
ML Service.
Dedicated process for Model Registry and Autonomous Learning.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from qtrader.ml.autonomous import AutonomousLoop

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("MLService")

class MLService:
    def __init__(self) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)
        
        self.ml_loop = AutonomousLoop()

    def handle_exit(self, *args: Any) -> None:
        logger.info("Shutdown signal received")
        self.running = False

    async def main_loop(self) -> None:
        logger.info("Starting ML Service...")
        # In a real deployment, this would start the background learning loops
        # and provide an API for real-time inference
        while self.running:
            logger.debug("ML Service Heartbeat - Registry active")
            await asyncio.sleep(15)

    async def run(self) -> None:
        await self.main_loop()

if __name__ == "__main__":
    service = MLService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal ML service crash: {e}")
        sys.exit(1)
