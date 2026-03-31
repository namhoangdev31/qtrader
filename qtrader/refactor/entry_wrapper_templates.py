"""Sovereign Entry Point Wrapper Templates.

This module provides standardized templates for wrapping all QTrader entry points 
with the TradingOrchestrator to ensure architectural compliance.
"""

from typing import Any, Protocol, TypeVar
from qtrader.core.orchestrator import TradingOrchestrator, SystemState
from qtrader.core.bus import EventBus

T = TypeVar("T")

class SovereignRunner(Protocol):
    """Protocol for a sovereign execution entry point."""
    def run(self) -> None: ...

# --- CLI / Script Template ---

class LiveSovereignRunner:
    """Standardized wrapper for live trading CLI entry points."""
    def __init__(self, orchestrator: TradingOrchestrator):
        self.orchestrator = orchestrator

    async def execute(self):
        # 1. Mandatory Sovereign Sequence
        self.orchestrator.initialize()
        self.orchestrator.validate()
        
        # 2. Sovereign Activation
        await self.orchestrator.run()

# --- API / Server Template ---

# (Implemented via FastAPI app.on_event("startup") hooks)
# See qtrader/api/api.py for concrete implementation.

# --- Backtest / Simulation Template ---

class BacktestSovereignRunner:
    """Standardized wrapper for historical simulation entry points."""
    def __init__(self, orchestrator: TradingOrchestrator):
        self.orchestrator = orchestrator

    async def execute(self):
        # 1. Mandatory Sovereign Sequence (Enforces same seeds/configs as live)
        self.orchestrator.initialize()
        self.orchestrator.validate()
        
        # 2. Simulation Execution
        # (Orchestrator handles the transition to RUNNING state)
        await self.orchestrator.execute_pipeline()
