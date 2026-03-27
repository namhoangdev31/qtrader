from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.scaling_governor")


class CapitalScalingGovernor:
    """
    Principal Capital Scaling Governor.

    Objective: Regulate capital expansion based on real-time risk, volatility,
    and operational stability metrics to prevent excessive scaling under instability.

    Model: Risk-Modulated Expansion ($Scale = \min(Growth, \frac{Score}{Vol})$).
    Constraint: Operational Lock (Drawdown freeze, Volatility throttling).
    """

    def __init__(self, max_scale: float = 0.05) -> None:
        """
        Initialize the institutional risk governor.
        """
        self._max_scale = max_scale

        # Telemetry for institutional situational awareness.
        self._scaling_block_count: int = 0
        self._cumulative_governance_factor: float = 0.0
        self._update_cycle_count: int = 0

    def regulate_expansion(
        self,
        target_growth: float,
        stability_score: float,
        volatility: float,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Produce a terminal governor report and compute the regulated scale factor.

        Forensic Logic:
        1. Drawdown Freeze: Expansion is 0.0 if the portfolio is in a recovery phase.
        2. Volatility Regulation: Scale factor is modulated by the Score/Vol efficiency.
        3. Spike Throttling: If volatility exceeds $Vol_{threshold}$, scale is blocked.
        4. Institutional Cap: Regulated scale is strictly capped at 5% per cycle.
        """
        start_time = time.time()

        # 1. Industrial Risk Verification.
        is_in_drawdown = metrics.get("in_drawdown", False)
        vol_threshold = float(metrics.get("vol_threshold", 5.0))  # Institutional Vol Cap.

        applied_scale = 0.0
        governance_status = "OPERATIONAL"
        rejection_reason = None

        if is_in_drawdown:
            applied_scale = 0.0
            governance_status = "DRAWDOWN_FREEZE"
            rejection_reason = "PORTFOLIO_IN_DRAWDOWN"
            self._scaling_block_count += 1
        elif volatility > vol_threshold:
            applied_scale = 0.0
            governance_status = "VOLATILITY_THROTTLE"
            rejection_reason = "VOLATILITY_SPIKE_DETECTED"
            self._scaling_block_count += 1
        else:
            # 2. Risk-Weighted Regulation.
            # Efficiency Factor = StabilityScore / TrailingVolatility
            efficiency_ratio = stability_score / max(0.0001, volatility)

            # Regulated Scale = min(target, efficiency_adjusted_growth)
            applied_scale = min(target_growth, efficiency_ratio)

            # Apply Institutional Scaling Cap (Scale_max).
            applied_scale = min(applied_scale, self._max_scale)
            applied_scale = max(0.0, applied_scale)

        # Telemetry Indexing.
        self._update_cycle_count += 1
        self._cumulative_governance_factor += applied_scale

        if rejection_reason:
            _LOG.warning(
                f"[GOVERNOR] SCALE_BLOCKED | Reason: {rejection_reason} | Vol: {volatility:.4f}"
            )
        else:
            _LOG.info(
                f"[GOVERNOR] SCALE_REGULATED | Scale: {applied_scale:.4f} | Vol: {volatility:.4f}"
            )

        # 3. Certification Artifact Construction.
        artifact = {
            "status": "GOVERNANCE_COMPLETE",
            "result": "PASS" if not rejection_reason else "BLOCK",
            "metrics": {
                "regulated_scale_factor": round(applied_scale, 4),
                "stability_vol_efficiency": round(stability_score / max(0.0001, volatility), 4),
                "active_scaling_blocks": self._scaling_block_count,
            },
            "governance_locks": {
                "drawdown_active": is_in_drawdown,
                "volatility_regime": "SPIKE" if volatility > vol_threshold else "STABLE",
            },
            "certification": {
                "institutional_max_scale": self._max_scale,
                "governance_mode": governance_status,
                "timestamp": time.time(),
                "real_validation_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_governance_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional risk governance.
        """
        avg_expansion = 0.0
        if self._update_cycle_count > 0:
            avg_expansion = self._cumulative_governance_factor / self._update_cycle_count

        return {
            "status": "GOVERNANCE_HEALTH",
            "total_scaling_blocks": self._scaling_block_count,
            "avg_regulated_expansion_rate": round(avg_expansion, 4),
            "governance_efficiency_score": round(1.0 / max(1, self._scaling_block_count), 4),
        }
