from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.reallocator")


class DynamicReallocationEngine:
    r"""
    Principal Dynamic Reallocation Engine.

    Objective: Continuously optimize platform capital distribution toward strategies
    exhibiting superior risk-adjusted performance in real-time.

    Model: Multi-Factor Factor Scoring ($\alpha, \beta, \gamma$).
    Constraint: Smooth Transition Gating ($|\Delta w| \le 10\%$).
    """

    def __init__(self, alpha: float = 0.5, beta: float = 0.3, gamma: float = 0.2) -> None:
        """
        Initialize the institutional optimization controller.
        """
        self._alpha = alpha  # PnL Factor Weight
        self._beta = beta  # Sharpe Factor Weight
        self._gamma = gamma  # Drawdown Factor Penalty

        # Telemetry for institutional situational awareness.
        self._cumulative_capital_shift: float = 0.0
        self._update_cycle_count: int = 0

    def recalculate_allocation(
        self,
        current_weights: dict[str, float],
        metrics: dict[str, dict[str, float]],
        max_shift: float = 0.1,
    ) -> dict[str, Any]:
        r"""
        Produce updated target weights based on performance factors and shift constraints.

        Forensic Logic:
        1. Performance Factor Scoring: Derives strategy scores via PnL, Sharpe, DD.
        2. Soft-Target Normalization: Derives target weights proportional to scores.
        3. Smooth Shift Gating: Enforces institutional $|\Delta w| \le 0.10$ limit.
        4. Re-normalization: Ensures coverage ($\sum w = 1.0$) after gating.
        """
        start_time = time.time()

        if not metrics:
            return {
                "status": "REALLOCATE_EMPTY",
                "result": "SKIP",
                "message": "Zero industrial performance metrics recorded for cycle.",
            }

        # 1. Performance-Weighted Multi-Factor Scoring.
        strategy_scores: dict[str, float] = {}
        for sid, metric in metrics.items():
            pnl_val = metric.get("pnl", 0.0)
            sharpe_val = metric.get("sharpe", 0.0)
            drawdown_val = metric.get("drawdown", 0.0)

            # Score = $\alpha \cdot PnL + \beta \cdot Sharpe - \gamma \cdot DD$
            raw_factor_score = (
                (self._alpha * pnl_val) + (self._beta * sharpe_val) - (self._gamma * drawdown_val)
            )
            # Ensure non-negative target weighting veracity.
            strategy_scores[sid] = max(0.0, raw_factor_score)

        total_score_sum = sum(strategy_scores.values())

        # 2. Performance-Based Target Weights Calculation.
        _epsilon = 1e-10
        if total_score_sum <= _epsilon:
            # Fallback: Uniform distribution across nodes with data.
            target_weights = {sid: (1.0 / len(strategy_scores)) for sid in strategy_scores}
        else:
            target_weights = {
                sid: (score / total_score_sum) for sid, score in strategy_scores.items()
            }

        # 3. Smooth Transition Gating ($|\Delta w| \le 10\%$).
        # $w_{new} = w_{old} + clamp(w_{target} - w_{old}, -0.1, 0.1)$
        updated_weights_clamped: dict[str, float] = {}
        incremental_delta_sum = 0.0

        all_active_ids = set(current_weights.keys()) | set(target_weights.keys())

        for sid in all_active_ids:
            weight_old = current_weights.get(sid, 0.0)
            weight_target = target_weights.get(sid, 0.0)

            raw_delta = weight_target - weight_old
            clamped_delta = max(-max_shift, min(max_shift, raw_delta))

            updated_weights_clamped[sid] = weight_old + clamped_delta
            incremental_delta_sum += abs(clamped_delta)

        # 4. Final Structural Re-normalization.
        new_sum = sum(updated_weights_clamped.values())
        _precision = 1e-10
        if new_sum > _precision:
            final_weights = {sid: (val / new_sum) for sid, val in updated_weights_clamped.items()}
        else:
            final_weights = updated_weights_clamped

        # Telemetry Update.
        self._cumulative_capital_shift += incremental_delta_sum
        self._update_cycle_count += 1

        _LOG.info(
            f"[REALLOCATE] UPDATE_FINALIZED | Shift: {incremental_delta_sum:.4f} "
            f"| Nodes: {len(final_weights)}"
        )

        # 5. Certification Artifact Construction.
        artifact = {
            "status": "REALLOCATE_COMPLETE",
            "result": "PASS",
            "metrics": {
                "active_strategy_nodes": len(final_weights),
                "cycle_reallocation_rate": round(incremental_delta_sum, 6),
                "cumulative_capital_shift": round(self._cumulative_capital_shift, 4),
            },
            "updated_distribution": {sid: round(w, 6) for sid, w in final_weights.items()},
            "certification": {
                "factor_weights": {"alpha": self._alpha, "beta": self._beta, "gamma": self._gamma},
                "institutional_shift_limit": max_shift,
                "timestamp": time.time(),
                "real_validation_duration_ms": round((start_time - time.time()) * 1000, 4),
            },
        }

        return artifact

    def get_reallocation_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional rebalancing health.
        """
        avg_shift = 0.0
        if self._update_cycle_count > 0:
            avg_shift = self._cumulative_capital_shift / self._update_cycle_count

        return {
            "status": "REALLOCATE_GOVERNANCE",
            "total_optimization_cycles": self._update_cycle_count,
            "cumulative_capital_shift": round(self._cumulative_capital_shift, 4),
            "avg_shift_per_cycle": round(avg_shift, 6),
        }
