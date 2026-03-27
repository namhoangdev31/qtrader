from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.allocator")


class CapitalAllocationEngine:
    r"""
    Principal Capital Allocation Engine.

    Objective: Distribute platform capital optimally across strategy ensembles proportional
    to their risk-adjusted Sharpe Ratios, while ensuring diversification veracity.

    Model: Sharpe-Weighted Distribution with Iterative Gating.
    Constraint: Diversification Cap ($w_i \le 20\%$).
    """

    def __init__(self, max_cap: float = 0.2) -> None:
        """
        Initialize the institutional allocation controller.
        """
        self._max_cap = max_cap
        # Telemetry for institutional situational awareness.
        self._current_distribution: dict[str, float] = {}
        self._capital_concentration: float = 0.0

    def allocate_capital(
        self,
        strategies: list[dict[str, Any]],
        total_capital: float,
    ) -> dict[str, Any]:
        r"""
        Produce a terminal allocation report for the strategical ensemble.

        Forensic Logic:
        1. Performance Filtering: Discards strategies with Sharpe <= 0.
        2. Performance Indexing: Derives initial weights proportional to Sharpe.
        3. Iterative Capping: Programmatically redistributes excess weight.
        4. Diversification Gating: Enforces $w_i \le 0.20$ for all strategy nodes.
        """
        start_time = time.time()

        # 1. Structural Performance Filtering.
        # Only allocate to strategies with positive alpha potential.
        performers = [s for s in strategies if float(s.get("sharpe", 0.0)) > 0.0]

        if not performers:
            _LOG.warning("[ALLOCATE] NO_PERFORMERS | Zero capital deployed.")
            return {
                "status": "ALLOCATION_EMPTY",
                "result": "SKIP",
                "message": "Zero strategies with Sharpe > 0 detected for target universe.",
            }

        # 2. Performance-Weighted Indexing.
        # $w_i^{initial} = Sharpe_i / \sum Sharpe_j$
        active_ids = [str(s["id"]) for s in performers]
        active_sharpes = [float(s["sharpe"]) for s in performers]
        total_sharpe = sum(active_sharpes)

        distribution_weights = {
            sid: (s / total_sharpe) for sid, s in zip(active_ids, active_sharpes, strict=True)
        }

        final_capped_weights: dict[str, float] = {}

        _epsilon = 1e-10

        while True:
            excess_exposure = 0.0
            available_ids = []

            for sid, weight in distribution_weights.items():
                if weight > self._max_cap:
                    excess_exposure += weight - self._max_cap
                    final_capped_weights[sid] = self._max_cap
                else:
                    available_ids.append(sid)

            # Convergence check: Exit if no structural excess remains.
            if excess_exposure <= _epsilon or not available_ids:
                break

            # Redistribute excess proportionally to existing weights.
            current_available_total = sum(distribution_weights[sid] for sid in available_ids)
            for sid in available_ids:
                distribution_weights[sid] += (
                    distribution_weights[sid] / current_available_total
                ) * excess_exposure

            # Remove capped nodes from the iterative redistribution cycle.
            for sid in final_capped_weights:
                distribution_weights.pop(sid, None)

        # Terminal weight reconstruction.
        final_weights = {**distribution_weights, **final_capped_weights}
        target_allocation_usd = {sid: w * total_capital for sid, w in final_weights.items()}

        # 4. Certification & Telemetry.
        self._current_distribution = target_allocation_usd
        self._capital_concentration = max(final_weights.values()) if final_weights else 0.0

        _LOG.info(
            f"[ALLOCATE] DISTRIBUTION_FINALIZED | Nodes: {len(final_weights)} "
            f"| Capital: {total_capital:.2f} | Concentration: {self._capital_concentration:.4f}"
        )

        # 5. Certification Artifact Construction.
        artifact = {
            "status": "ALLOCATION_COMPLETE",
            "result": "PASS",
            "metrics": {
                "active_strategy_nodes": len(final_weights),
                "total_capital_usd": round(total_capital, 2),
                "deployed_capital_usd": round(sum(target_allocation_usd.values()), 2),
                "max_concentration_score": round(self._capital_concentration, 4),
            },
            "distribution_map": {sid: round(w, 6) for sid, w in final_weights.items()},
            "certification": {
                "institutional_cap_limit": self._max_cap,
                "timestamp": time.time(),
                "real_validation_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_allocation_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional asset allocation.
        """
        entropy = 1.0 - self._capital_concentration if self._capital_concentration > 0 else 0.0

        return {
            "status": "ALLOCATION_GOVERNANCE",
            "current_max_concentration": round(self._capital_concentration, 4),
            "diversification_entropy": round(entropy, 4),
            "active_capital_nodes": len(self._current_distribution),
        }
