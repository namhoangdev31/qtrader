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

from qtrader.core.orchestrator import TradingOrchestrator, SystemState
from qtrader.core.bus import EventBus


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("OrchestratorService")

# FastAPI for monitoring
app = FastAPI(title="QTrader Global Orchestrator Service")

# Sovereign Orchestrator Instance (Injected at runtime)
# We initialize it here for the standalone service
orch = TradingOrchestrator(
    event_bus=EventBus(),
    market_data_adapter=object(),
    alpha_modules=[],
    feature_validator=None, # type: ignore
    strategies=[],
    ensemble_strategy=None, # type: ignore
    portfolio_allocator=None, # type: ignore
    runtime_risk_engine=None, # type: ignore
    oms_adapter=None, # type: ignore
)

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "state": orch._state.name}

@app.get("/status")
async def get_status() -> dict[str, Any]:
    """Retrieve fund-wide status from the sovereign orchestrator."""
    return {
        "state": orch._state.name,
        "boot_time": orch._boot_time,
        "authorized": True
    }

@app.post("/kill")
async def engage_kill_switch(reason: str = "Manual Trigger") -> dict[str, str]:
    await orch.halt_core(reason)
    return {"status": "HALTED", "reason": reason}


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
        logger.info("Starting Sovereign Orchestrator Service...")
        
        # 1. Initialize Sovereign Orchestrator
        orch.initialize()
        
        # 2. Start Execution Pipeline
        await orch.execute_pipeline()


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
