from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.position_sizing")


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
