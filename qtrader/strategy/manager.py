from __future__ import annotations
import logging
from typing import Any
from qtrader.core.dynamic_config import config_manager

logger = logging.getLogger("qtrader.strategy.manager")


class StrategyManager:
    def __init__(self, symbol: str) -> None:
        self._strategies: dict[str, Any] = {}
        self.active_strategy_name = config_manager.get("active_strategy", "MOMENTUM")
        logger.info(f"[STRATEGY_MANAGER] Initialized with {self.active_strategy_name}")

    @property
    def active_strategy(self) -> Any:
        target = config_manager.get("active_strategy", "MOMENTUM")
        if target not in self._strategies:
            logger.warning(
                f"[STRATEGY_MANAGER] Strategy {target} not found, falling back to MOMENTUM"
            )
            target = "MOMENTUM"
        if target != self.active_strategy_name:
            logger.info(
                f"[STRATEGY_MANAGER] SWAPPING METHODOLOGY: {self.active_strategy_name} -> {target}"
            )
            self.active_strategy_name = target
        return self._strategies[target]

    def get_strategy_names(self) -> list[str]:
        return list(self._strategies.keys())
