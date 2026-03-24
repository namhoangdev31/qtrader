"""
Orchestrator Service.
Master process for Global Fund Orchestration.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

import uvicorn
from fastapi import FastAPI

from qtrader.core.global_orchestrator import GlobalOrchestrator
from qtrader.core.orchestrator import TradingOrchestrator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("OrchestratorService")

# FastAPI for monitoring
app = FastAPI(title="QTrader Global Orchestrator")
global_orch = GlobalOrchestrator()

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "mode": global_orch._mode.value}

@app.get("/status")
async def get_status() -> dict[str, Any]:
    return await global_orch.get_total_fund_risk()

@app.post("/kill")
async def engage_kill_switch(reason: str = "Manual Trigger") -> dict[str, str]:
    await global_orch.engage_global_kill_switch(reason)
    return {"status": "STOPPED", "reason": reason}

class OrchestratorService:
    def __init__(self) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)

    def handle_exit(self, *args: Any) -> None:
        logger.info("Shutdown signal received")
        self.running = False

    async def run_api(self) -> None:
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()

    async def main_loop(self) -> None:
        logger.info("Starting Global Orchestrator Service...")
        
        # Register default orchestrators (Example: Crypto and Forex)
        crypto_orch = TradingOrchestrator() # In real usage, pass specific config
        global_orch.register_orchestrator("crypto_fund", crypto_orch)
        
        # Start the Global Orchestrator
        # This will run all child orchestrators concurrently
        await global_orch.start()

    async def run(self) -> None:
        await asyncio.gather(
            self.run_api(),
            self.main_loop()
        )

if __name__ == "__main__":
    service = OrchestratorService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal service crash: {e}")
        sys.exit(1)
