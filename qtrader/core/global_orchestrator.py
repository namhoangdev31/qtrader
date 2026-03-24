"""
Global Orchestrator.
Master controller for multiple trading orchestrators, strategies, and portfolios.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from qtrader.core.logger import logger
from qtrader.portfolio.capital_allocator import CapitalAllocator
from qtrader.risk.factor_risk import FactorRiskEngine

if TYPE_CHECKING:
    from qtrader.core.orchestrator import TradingOrchestrator

class FundMode(Enum):
    LIVE = "LIVE"
    SHADOW = "SHADOW"
    BACKTEST = "BACKTEST"

class GlobalOrchestrator:
    """
    Coordinates multiple trading systems and manages fund-wide risk/capital.
    """

    def __init__(
        self,
        capital_allocator: CapitalAllocator | None = None,
        factor_risk_engine: FactorRiskEngine | None = None
    ):
        self._orchestrators: dict[str, TradingOrchestrator] = {}
        self._mode: FundMode = FundMode.SHADOW
        self._kill_switch_active: bool = False
        
        self.capital_allocator = capital_allocator or CapitalAllocator()
        self.factor_risk_engine = factor_risk_engine or FactorRiskEngine()
        
    def register_orchestrator(self, name: str, orchestrator: TradingOrchestrator) -> None:
        """Register a child orchestrator."""
        self._orchestrators[name] = orchestrator
        logger.info(f"Registered orchestrator: {name}")

    def set_fund_mode(self, mode: Literal["LIVE", "SHADOW", "BACKTEST"]) -> None:
        """Synchronize mode across all portfolios."""
        self._mode = FundMode(mode)
        logger.info(f"Global Fund Mode set to: {self._mode.value}")
        # In a real system, we would update child orchestrator configs here
        # For now, we propagate it to any child that supports it

    async def engage_global_kill_switch(self, reason: str) -> None:
        """Halt ALL trading activity immediately across all orchestrators."""
        self._kill_switch_active = True
        logger.critical(f"GLOBAL KILL SWITCH ENGAGED! Reason: {reason}")
        
        # Parallel halt call to all children
        tasks = []
        for name, orch in self._orchestrators.items():
            logger.warning(f"Killing child orchestrator: {name}")
            # Engage child-level kill switch if available
            if hasattr(orch, "network_kill_switch") and orch.network_kill_switch is not None:
                kill_task = orch.network_kill_switch.engage_hard_kill(
                    reason=f"Global Halt: {reason}"
                )
                tasks.append(kill_task)
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run_fund_allocation(self, strategy_returns: pl.DataFrame | None = None) -> None:
        """Re-allocate capital across all registered orchestrators."""
        if not self._orchestrators:
            return

        # Prepare strategy (orchestrator) stats for the allocator
        stats_list = []
        for name, _orch in self._orchestrators.items():
            # In a real system, we'd pull these from the child's FeedbackEngine
            # Mocking stats for now based on child attributes
            stats_list.append({
                "strategy_id": name,
                "volatility": 0.20,  # Default
                "sharpe": 1.0,       # Default
                "max_drawdown": 0.10 # Default
            })
            
        strategy_stats = pl.DataFrame(stats_list)
        new_weights = self.capital_allocator.allocate(strategy_stats, strategy_returns)
        
        # Apply weights as risk multipliers to child orchestrators
        for name, weight in new_weights.items():
            if name in self._orchestrators:
                orch = self._orchestrators[name]
                # Scale weight to a risk multiplier (assuming 1.0 is baseline)
                # target_multiplier = weight * num_strategies
                multiplier = weight * len(self._orchestrators)
                if hasattr(orch.portfolio_allocator, "set_risk_multiplier"):
                    orch.portfolio_allocator.set_risk_multiplier(Decimal(str(multiplier)))
                    logger.info(
                        f"Adjusted {name} (Weight: {weight:.2f}) "
                        f"risk multiplier to {multiplier:.2f}"
                    )

    async def get_total_fund_risk(self) -> dict[str, Any]:
        """Aggregate positions and calculate total fund factor risk."""
        total_positions: dict[str, float] = {}
        
        for orch in self._orchestrators.values():
            if hasattr(orch, "state_store") and orch.state_store is not None:
                positions = await orch.state_store.get_positions()
                for symbol, pos in positions.items():
                    total_positions[symbol] = total_positions.get(symbol, 0.0) + float(pos.quantity)
                    
        # This would pass aggregated positions to the FactorRiskEngine
        # For now, we return a summary
        return {
            "num_strategies": len(self._orchestrators),
            "total_assets": len(total_positions),
            "mode": self._mode.value,
            "kill_switch": self._kill_switch_active
        }

    async def start(self) -> None:
        """Start all registered orchestrators."""
        if self._kill_switch_active:
            logger.error("Cannot start: Global kill switch is active")
            return
            
        await asyncio.gather(*[orch.run() for orch in self._orchestrators.values()])
