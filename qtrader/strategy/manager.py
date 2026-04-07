from __future__ import annotations

import logging
from typing import Any

from qtrader.core.dynamic_config import config_manager
from qtrader.strategy.base import BaseStrategy
from qtrader.strategy.momentum import TimeSeriesMomentum
from qtrader.strategy.probabilistic_strategy import ProbabilisticStrategy
from qtrader.strategy.ensemble_strategy import EnsembleStrategy

logger = logging.getLogger("qtrader.strategy.manager")


class StrategyManager:
    """Manages dynamic switching between trading strategies based on AI configuration."""

    def __init__(self, symbol: str) -> None:
        # Initialize available strategies
        momentum = TimeSeriesMomentum(symbol=symbol)
        probabilistic = ProbabilisticStrategy(symbol=symbol)
        
        self._strategies: dict[str, Any] = {
            "MOMENTUM": momentum,
            "PROBABILISTIC": probabilistic,
            "ENSEMBLE": EnsembleStrategy(strategies=[momentum, probabilistic]),
        }
        self.active_strategy_name = config_manager.get("active_strategy", "MOMENTUM")
        logger.info(f"[STRATEGY_MANAGER] Initialized with {self.active_strategy_name}")

    @property
    def active_strategy(self) -> Any:
        """Get the currently active strategy instance."""
        target = config_manager.get("active_strategy", "MOMENTUM")
        if target not in self._strategies:
            logger.warning(f"[STRATEGY_MANAGER] Strategy {target} not found, falling back to MOMENTUM")
            target = "MOMENTUM"
        
        if target != self.active_strategy_name:
            logger.info(f"[STRATEGY_MANAGER] SWAPPING METHODOLOGY: {self.active_strategy_name} -> {target}")
            self.active_strategy_name = target
            
        return self._strategies[target]

    def get_strategy_names(self) -> list[str]:
        """Return list of available strategy identifiers."""
        return list(self._strategies.keys())
