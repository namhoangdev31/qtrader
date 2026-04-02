from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from math import floor
from typing import Any

_LOG = logging.getLogger(__name__)


__all__ = ["ATRPositionSizer", "PositionSizer", "RiskAdaptivePositionSizer", "RiskParitySizer", "VolTargetSizer"]


class RiskAdaptivePositionSizer:
    r"""
    Principal Position Sizing Engine.

    Objective: Dynamically adjust trade sizes based on market volatility to maintain
    constant risk contribution across different market regimes.

    Model: Inverse-Volatility Scaling ($Size = BaseSize \cdot \frac{TargetVol}{\sigma}$).
    Constraint: Absolute Exposure Capping ($Size \le Size_{max}$).
    """

    def __init__(self, size_max: float = 1.0) -> None:
        """
        Initialize the institutional position sizer.
        """
        self._size_max = size_max

        # Telemetry for institutional situational awareness.
        self._cumulative_size: float = 0.0
        self._decision_count: int = 0
        self._cumulative_volatility: float = 0.0

    def calculate_adaptive_size(
        self,
        base_size: float,
        volatility: float,
        constraints: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        r"""
        Produce a terminal sizing report and compute the adaptive position size.

        Forensic Logic:
        1. Volatility Modulation: Factor is computed as $TargetVol / \sigma$.
        2. Exposure Scaling: $Size = BaseSize \cdot Factor$.
        3. Constraint Gating: Derived size is clamped by institutional max/min bounds.
        """
        start_time = time.time()

        # 1. Industrial Configuration.
        config = constraints or {}
        target_vol = config.get("target_vol", 0.01)  # Default 1% vol target.
        size_limit = config.get("size_max", self._size_max)
        size_floor = config.get("size_min", 0.0)

        # 2. Inverse-Volatility Factor Calculation.
        # Use a volatility floor (epsilon) to prevent division errors.
        vol_epsilon = 1e-6
        modulation_factor = target_vol / max(vol_epsilon, volatility)

        # 3. Size Computation and Constraint Clamping.
        # Adjusted Size = Base * (TargetVol / CurrentVol)
        raw_adjusted_size = base_size * modulation_factor

        # Strict clamping to institutional exposure limits.
        applied_size = min(raw_adjusted_size, size_limit)
        applied_size = max(applied_size, size_floor)

        # 4. Telemetry Indexing.
        self._decision_count += 1
        self._cumulative_size += applied_size
        self._cumulative_volatility += volatility

        _LOG.info(
            f"[POSITION] SIZE_ADAPTED | Vol: {volatility:.4f} "
            f"| Factor: {modulation_factor:.4f} | Final: {applied_size:.4f}"
        )

        # 5. Certification Artifact Construction.
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
        """
        situational awareness for institutional volatility-aware exposure.
        """
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
    """AQR-style volatility targeting. Scales position to hit target_vol."""

    target_vol: float = 0.10
    lookback: int = 20

    def size(self, symbol: str, realized_vol: float, capital: float) -> float:
        """Compute target dollar notional for a symbol.

        Args:
            symbol: Instrument identifier (unused, for interface completeness).
            realized_vol: Realised or estimated volatility (annualised or target-consistent).
            capital: Total capital allocated to the strategy.

        Returns:
            Target dollar position value. Returns 0.0 if volatility is non-positive.
        """
        if realized_vol <= 0.0 or capital <= 0.0:
            return 0.0
        position_value = (self.target_vol / realized_vol) * capital
        return float(position_value)


@dataclass(slots=True)
class ATRPositionSizer:
    """Size based on ATR for constant dollar risk per trade."""

    risk_per_trade_pct: float = 0.01

    def size(self, capital: float, atr: float, price: float) -> float:
        """Compute number of shares based on ATR and risk budget.

        Args:
            capital: Total trading capital.
            atr: Average True Range in price units.
            price: Current asset price.

        Returns:
            Number of shares to trade (float, already floored). Returns 0.0 for
            non-positive ATR or price.
        """
        if atr <= 0.0 or price <= 0.0 or capital <= 0.0:
            return 0.0
        dollar_risk_per_share = atr
        total_risk_budget = capital * self.risk_per_trade_pct
        raw_shares = total_risk_budget / dollar_risk_per_share
        return float(max(0, floor(raw_shares)))


@dataclass(slots=True)
class RiskParitySizer:
    """Equal risk contribution across all assets."""

    def size(self, vols: dict[str, float], capital: float) -> dict[str, float]:
        """Allocate capital according to inverse-volatility weights.

        Args:
            vols: Mapping of symbol to volatility (must be positive to receive allocation).
            capital: Total capital to distribute.

        Returns:
            Dictionary of symbol to dollar allocation, summing approximately to capital.
        """
        positive = {s: v for s, v in vols.items() if v > 0.0}
        if not positive or capital <= 0.0:
            return {s: 0.0 for s in vols}

        inv_vol = {s: 1.0 / v for s, v in positive.items()}
        total = sum(inv_vol.values())
        if total <= 0.0:
            n = len(positive)
            equal_alloc = capital / float(n)
            return {s: equal_alloc for s in vols}

        weights = {s: v / total for s, v in inv_vol.items()}
        allocations = {s: w * capital for s, w in weights.items()}

        return {s: allocations.get(s, 0.0) for s in vols}


class PositionSizer:
    """
    Computes optimal position sizes using risk-management heuristics.

    Mathematical Model:
    - Kelly Criterion: f = (p(b+1) - 1) / b
    - Constraints: 0 <= f <= f_max
    """

    @staticmethod
    def compute_kelly_fraction(
        win_prob: float, win_loss_ratio: float, f_max: float = 1.0
    ) -> float:
        """
        Compute the Kelly fraction for optimal positioning.

        Args:
            win_prob: Probability of a winning trade (p).
            win_loss_ratio: Average win amount / Average loss amount (b).
            f_max: Maximum allowed fraction (capping leverage).

        Returns:
            Optimal fraction f in [0, f_max].
        """
        if win_loss_ratio <= 0:
            return 0.0

        # Kelly Formula: f = (p * (b + 1) - 1) / b
        # Expected value must be positive: p * (b + 1) > 1
        raw_f = (win_prob * (win_loss_ratio + 1) - 1) / win_loss_ratio

        # Clamp between 0 and f_max
        return max(0.0, min(raw_f, f_max))
