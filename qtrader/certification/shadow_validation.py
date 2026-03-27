from __future__ import annotations

import logging
import statistics
import time
from enum import Enum, auto
from typing import Any

_LOG = logging.getLogger("qtrader.certification.shadow_validation")


class MarketRegime(Enum):
    """
    Institutional Market Regimes.
    Defines the structural classification for shadow-mode performance audits.
    """

    TRENDING = auto()
    MEAN_REVERTING = auto()
    HIGH_VOLATILITY = auto()
    LOW_LIQUIDITY = auto()


class ShadowValidationEngine:
    """
    Principal Shadow Validation Engine.

    Objective: Validate that a shadow strategy out-performs its baseline (TWAP/VWAP)
    across all identified market regimes while maintaining structural consistency.

    Model: Regime-Relative Performance Delta ($\Delta = PnL_{strategy} - PnL_{baseline}$).
    Constraint: Variance Bound ($\sigma \le \sigma_{max}$) and Total Regime Coverage.
    """

    def __init__(self, sigma_max_bound: float = 0.05) -> None:
        """
        Initialize the institutional shadow controller.
        """
        self._sigma_max = sigma_max_bound
        # Telemetry for institutional situational awareness.
        self._stats = {"regime_points_count": 0, "cumulative_delta": 0.0}

    def evaluate_shadow_performance(
        self, regime_results: dict[MarketRegime, dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Produce a terminal shadow validation report across diverse market regimes.

        Forensic Logic:
        1. Diversity Audit: Enforces that all mandated regimes are present.
        2. Performance Delta: Computes the edge ($\Delta$) relative to baseline TWAP.
        3. Consistency Gating: Enforces a variance bound to filter stochastic luck.
        """
        start_time = time.time()

        mandated_regimes = set(MarketRegime)
        observed_regimes = set(regime_results.keys())
        has_diversity_compliance = mandated_regimes.issubset(observed_regimes)

        regime_evaluations = {}
        performance_pass = True
        pnl_deltas = []

        for regime, data in regime_results.items():
            delta = data["strategy_pnl"] - data["baseline_pnl"]
            pnl_deltas.append(delta)

            regime_pash = delta >= 0
            if not regime_pash:
                performance_pass = False

            regime_evaluations[regime.name] = {
                "performance_delta": round(delta, 6),
                "passed": regime_pash,
                "strategy_pnl": data["strategy_pnl"],
                "baseline_pnl": data["baseline_pnl"],
            }

        performance_variance = statistics.variance(pnl_deltas) if len(pnl_deltas) > 1 else 0.0
        is_consistent = performance_variance <= self._sigma_max

        overall_ready = has_diversity_compliance and performance_pass and is_consistent
        final_result = "PASS" if overall_ready else "FAIL"

        avg_delta = statistics.mean(pnl_deltas) if pnl_deltas else 0.0
        self._stats["cumulative_delta"] += avg_delta
        self._stats["regime_points_count"] += len(regime_results)

        if overall_ready:
            _LOG.info(
                f"[SHADOW] VALIDATION_PASS | Avg Delta: {avg_delta:.6f} "
                f"| Variance: {performance_variance:.6f}"
            )
        else:
            _LOG.error(
                f"[SHADOW] VALIDATION_FAIL | Diversity: {has_diversity_compliance} "
                f"| Alpha: {performance_pass} | Consistency: {is_consistent}"
            )

        artifact = {
            "status": "SHADOW_COMPLETE",
            "result": final_result,
            "metrics": {
                "regime_count": len(regime_results),
                "regime_diversity_met": has_diversity_compliance,
                "variance_consistency_met": is_consistent,
                "average_performance_delta": round(avg_delta, 6),
            },
            "regime_breakdown": regime_evaluations,
            "certification": {
                "measured_variance": round(performance_variance, 6),
                "timestamp": time.time(),
                "real_sim_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_shadow_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional strategy certification.
        """
        return {
            "status": "SHADOW_CERTIFICATION",
            "total_regime_observations": self._stats["regime_points_count"],
            "weighted_cumulative_delta": round(self._stats["cumulative_delta"], 6),
        }
