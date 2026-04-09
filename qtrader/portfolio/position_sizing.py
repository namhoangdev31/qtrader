from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from math import floor
from typing import Any

_LOG = logging.getLogger(__name__)
__all__ = [
    "ATRPositionSizer",
    "PositionSizer",
    "RiskAdaptivePositionSizer",
    "RiskParitySizer",
    "VolTargetSizer",
]


class RiskAdaptivePositionSizer:
    def __init__(self, size_max: float = 1.0) -> None:
        self._size_max = size_max
        self._cumulative_size: float = 0.0
        self._decision_count: int = 0
        self._cumulative_volatility: float = 0.0

    def calculate_adaptive_size(
        self, base_size: float, volatility: float, constraints: dict[str, float] | None = None
    ) -> dict[str, Any]:
        start_time = time.time()
        config = constraints or {}
        target_vol = config.get("target_vol", 0.01)
        size_limit = config.get("size_max", self._size_max)
        size_floor = config.get("size_min", 0.0)
        vol_epsilon = 1e-06
        modulation_factor = target_vol / max(vol_epsilon, volatility)
        raw_adjusted_size = base_size * modulation_factor
        applied_size = min(raw_adjusted_size, size_limit)
        applied_size = max(applied_size, size_floor)
        self._decision_count += 1
        self._cumulative_size += applied_size
        self._cumulative_volatility += volatility
        _LOG.info(
            f"[POSITION] SIZE_ADAPTED | Vol: {volatility:.4f} | Factor: {modulation_factor:.4f} | Final: {applied_size:.4f}"
        )
        artifact = {
            "status": "SIZING_COMPLETE",
            "result": "PASS",
            "metrics": {
                "calculated_position_size": round(applied_size, 4),
                "volatility_modulation_factor": round(modulation_factor, 4),
                "unconstrained_raw_size": round(raw_adjusted_size, 4),
            },
            "governance": {
                "size_max_applied": size_limit,
                "size_min_applied": size_floor,
                "volatility_floor_active": volatility < vol_epsilon,
            },
            "certification": {
                "target_vol_anchor": target_vol,
                "trailing_volatility": round(volatility, 4),
                "timestamp": time.time(),
                "sizing_latency_ms": round((time.time() - start_time) * 1000, 4),
            },
        }
        return artifact

    def get_sizing_telemetry(self) -> dict[str, Any]:
        avg_size = 0.0
        avg_vol = 0.0
        if self._decision_count > 0:
            avg_size = self._cumulative_size / self._decision_count
            avg_vol = self._cumulative_volatility / self._decision_count
        return {
            "status": "SIZING_GOVERNANCE",
            "avg_position_size_observed": round(avg_size, 4),
            "avg_volatility_observed": round(avg_vol, 4),
            "lifecycle_decision_count": self._decision_count,
        }


@dataclass(slots=True)
class VolTargetSizer:
    target_vol: float = 0.1
    lookback: int = 20

    def size(self, symbol: str, realized_vol: float, capital: float) -> float:
        if realized_vol <= 0.0 or capital <= 0.0:
            return 0.0
        position_value = self.target_vol / realized_vol * capital
        return position_value


@dataclass(slots=True)
class ATRPositionSizer:
    risk_per_trade_pct: float = 0.01

    def size(self, capital: float, atr: float, price: float) -> float:
        if atr <= 0.0 or price <= 0.0 or capital <= 0.0:
            return 0.0
        dollar_risk_per_share = atr
        total_risk_budget = capital * self.risk_per_trade_pct
        raw_shares = total_risk_budget / dollar_risk_per_share
        return max(0, floor(raw_shares))


@dataclass(slots=True)
class RiskParitySizer:
    def size(self, vols: dict[str, float], capital: float) -> dict[str, float]:
        positive = {s: v for (s, v) in vols.items() if v > 0.0}
        if not positive or capital <= 0.0:
            return {s: 0.0 for s in vols}
        inv_vol = {s: 1.0 / v for (s, v) in positive.items()}
        total = sum(inv_vol.values())
        if total <= 0.0:
            n = len(positive)
            equal_alloc = capital / n
            return {s: equal_alloc for s in vols}
        weights = {s: v / total for (s, v) in inv_vol.items()}
        allocations = {s: w * capital for (s, w) in weights.items()}
        return {s: allocations.get(s, 0.0) for s in vols}


class PositionSizer:
    @staticmethod
    def compute_kelly_fraction(win_prob: float, win_loss_ratio: float, f_max: float = 1.0) -> float:
        if win_loss_ratio <= 0:
            return 0.0
        raw_f = (win_prob * (win_loss_ratio + 1) - 1) / win_loss_ratio
        return max(0.0, min(raw_f, f_max))
