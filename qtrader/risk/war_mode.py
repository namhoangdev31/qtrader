from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

_LOG = logging.getLogger("qtrader.risk.war_mode")
try:
    from qtrader_core import WarModeState as RustWarModeState
except ImportError as e:
    _LOG.error(
        "[WAR_MODE] Institutional Risk Core (qtrader_core) is missing. System startup blocked."
    )
    raise ImportError(
        "qtrader_core is a mandatory dependency for institutional safety orchestration"
    ) from e


class WarModeState(str, Enum):
    NORMAL = "NORMAL"
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    DEACTIVATING = "DEACTIVATING"
    WAR_MODE = "WAR_MODE"
    HALTED = "HALTED"


@dataclass(slots=True)
class WarModeConfig:
    dd_trigger_pct: float = 0.15
    daily_loss_trigger: float = 50000.0
    volatility_trigger: float = 3.0
    anomaly_trigger: float = 0.95


class WarModeEngine:
    def __init__(self, rust_engine: Any, config: WarModeConfig | None = None) -> None:
        self.config = config or WarModeConfig()
        self._rust_engine = rust_engine
        self._activation_count: int = 0

    def evaluate_state(
        self,
        drawdown_pct: float,
        daily_loss: float,
        volatility_ratio: float,
        anomaly_intensity: float,
    ) -> WarModeState:
        rust_state = self._rust_engine.get_state()
        state_str = str(rust_state).split(".")[-1].upper()
        if "WAR" in state_str:
            return WarModeState.WAR_MODE
        if "HALT" in state_str:
            return WarModeState.HALTED
        return WarModeState.NORMAL

    def check_order_allowed(
        self, symbol: str, side: str, is_hedge: bool, is_unwind: bool
    ) -> tuple[bool, str]:
        state = self.evaluate_state(0, 0, 0, 0)
        if state == WarModeState.NORMAL:
            return (True, "Normal operations")
        if state == WarModeState.HALTED:
            return (False, "SYSTEM_HALTED: All trading blocked")
        if is_hedge or is_unwind:
            return (True, f"War Mode: Only position reduction allowed ({state})")
        return (False, f"War Mode blocked: New positions restricted ({state})")

    def get_status(self) -> dict[str, Any]:
        rust_state = self._rust_engine.get_state()
        return {
            "state": str(rust_state),
            "engine": "RUST_CORE",
            "is_active": "NORMAL" not in str(rust_state),
            "config": {
                "dd_trigger": self.config.dd_trigger_pct,
                "daily_loss": self.config.daily_loss_trigger,
            },
        }

    @staticmethod
    def _now() -> float:
        return time.time()
