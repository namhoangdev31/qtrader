from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.drawdown_controller")


@dataclass(slots=True)
class DrawdownConfig:
    stop_level: float = 0.15
    heavy_reduce_level: float = 0.1
    light_reduce_level: float = 0.05
    heavy_reduce_factor: float = 0.5
    light_reduce_factor: float = 0.75
    lockout_threshold: float = 0.15


class LiveDrawdownController:
    def __init__(self, config: DrawdownConfig | None = None) -> None:
        self.config = config or DrawdownConfig()
        self._historical_max_drawdown: float = 0.0
        self._cumulative_adjustment_count: int = 0

    def calculate_risk_adjustment(
        self, current_equity: float, peak_equity: float
    ) -> dict[str, Any]:
        start_time = time.time()
        if peak_equity <= 0:
            return {
                "status": "DD_CONTROL_ERROR",
                "result": "FAIL",
                "message": "Institutional peak equity must be strictly positive.",
            }
        raw_drawdown = (peak_equity - current_equity) / peak_equity
        current_drawdown = max(0.0, raw_drawdown)
        applied_risk_factor = 1.0
        risk_action_level = "NORMAL"
        if current_drawdown >= self.config.stop_level:
            applied_risk_factor = 0.0
            risk_action_level = "STOP"
        elif current_drawdown >= self.config.heavy_reduce_level:
            applied_risk_factor = self.config.heavy_reduce_factor
            risk_action_level = "REDUCE_50"
        elif current_drawdown >= self.config.light_reduce_level:
            applied_risk_factor = self.config.light_reduce_factor
            risk_action_level = "REDUCE_25"
        else:
            applied_risk_factor = 1.0
            risk_action_level = "NORMAL"
        self._historical_max_drawdown = max(self._historical_max_drawdown, current_drawdown)
        if risk_action_level != "NORMAL":
            self._cumulative_adjustment_count += 1
            _LOG.warning(
                f"[DD_CONTROL] RISK_ADJUSTED | Level: {risk_action_level} | DD: {current_drawdown:.4f} | Factor: {applied_risk_factor}"
            )
        else:
            _LOG.info(f"[DD_CONTROL] STATE_SECURE | DD: {current_drawdown:.4f}")
        artifact = {
            "status": "DD_CONTROL_COMPLETE",
            "result": "PASS" if applied_risk_factor > 0 else "HALTED",
            "action": risk_action_level,
            "metrics": {
                "current_drawdown_percent": round(current_drawdown * 100, 2),
                "risk_adjustment_factor": round(applied_risk_factor, 4),
                "cumulative_actions_taken": self._cumulative_adjustment_count,
            },
            "certification": {
                "peak_drawdown_observed": round(self._historical_max_drawdown, 4),
                "timestamp": time.time(),
                "validation_latency_ms": round((time.time() - start_time) * 1000, 4),
            },
        }
        return artifact

    def get_drawdown_telemetry(self) -> dict[str, Any]:
        return {
            "status": "DD_GOVERNANCE",
            "maxly_historical_drawdown": round(self._historical_max_drawdown, 4),
            "governance_event_count": self._cumulative_adjustment_count,
            "lockout_active": self._historical_max_drawdown >= self.config.lockout_threshold,
        }
