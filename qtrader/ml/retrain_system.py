from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

_LOG = logging.getLogger("qtrader.ml.retrain_system")


@dataclass(slots=True, frozen=True)
class RetrainDecision:
    """
    Industrial MLOps Retraining Decision.
    """

    trigger: bool
    psi: float
    performance_drop: float
    reason: str


class RetrainSystem:
    """
    Principal Controlled Retraining Engine.

    Objective: Monitor data drift and performance decay to trigger
    model retraining cycles only when statistically necessary.
    Enforces the 'Drift-First' principle to prevent model staleness
    without inducing unnecessary training overhead.
    """

    def __init__(self, psi_threshold: float = 0.25, performance_drop_delta: float = 0.15) -> None:
        """
        Initialize the retraining monitor.

        Args:
            psi_threshold: PSI limit (> 0.25 is generally significant drift).
            performance_drop_delta: Absolute decay allowed from baseline.
        """
        self._psi_threshold = psi_threshold
        self._delta = performance_drop_delta

        # Telemetry
        self._stats = {"retrain_count": 0, "max_psi": 0.0}

    def compute_psi(self, expected: np.ndarray[Any, Any], actual: np.ndarray[Any, Any]) -> float:
        """
        Compute the Population Stability Index (PSI).

        Formula: PSI = sum((p - q) * ln(p / q))
        Ensures vectorized execution for real-time monitoring.
        """
        # Ensure probability distributions (normalize if raw counts)
        sum_p = np.sum(expected)
        sum_q = np.sum(actual)

        p = expected / sum_p if sum_p > 0 else expected
        q = actual / sum_q if sum_q > 0 else actual

        # Epsilon safety to prevent log(0) or division by zero
        eps = 1e-6
        p = np.clip(p, eps, 1.0)
        q = np.clip(q, eps, 1.0)

        # Vectorized PSI Calculation
        psi_values = (p - q) * np.log(p / q)
        return float(np.sum(psi_values))

    def evaluate(
        self,
        expected_dist: np.ndarray[Any, Any],
        actual_dist: np.ndarray[Any, Any],
        current_perf: float,
        baseline_perf: float,
    ) -> RetrainDecision:
        """
        Determine if retraining is authorized based on drift and decay.

        Args:
            expected_dist: Binned distribution from training population.
            actual_dist: Binned distribution from live population.
            current_perf: Current realized performance metric (e.g., Accuracy).
            baseline_perf: Historical baseline performance for comparison.

        Returns:
            RetrainDecision containing trigger status and justification.
        """
        # 1. Compute Data Drift (PSI)
        psi = self.compute_psi(expected_dist, actual_dist)

        # 2. Compute Performance Decay
        # Assumes higher performance is better (e.g., Sharpe, Accuracy)
        perf_drop = max(0.0, baseline_perf - current_perf)

        # 3. Decision Logic
        trigger = False
        reason = "NOMINAL_OPERATING_CONDITIONS"

        if psi > self._psi_threshold:
            trigger = True
            reason = f"SIGNIFICANT_DATA_DRIFT_IDENTIFIED: PSI={psi:.4f}"

        elif perf_drop > self._delta:
            trigger = True
            reason = f"PERFORMANCE_DECAY_DETECTED: Drop={perf_drop:.4f}"

        # 4. Telemetry Update
        if trigger:
            self._stats["retrain_count"] += 1
            _LOG.warning(f"[RETRAIN] {reason}")

        self._stats["max_psi"] = max(self._stats["max_psi"], psi)

        return RetrainDecision(
            trigger=trigger,
            psi=round(psi, 4),
            performance_drop=round(perf_drop, 4),
            reason=reason,
        )

    def get_retrain_report(self) -> dict[str, Any]:
        """
        Generate MLOps situational awareness summary.
        """
        return {
            "status": "RETRAIN_REPORT",
            "total_triggers": self._stats["retrain_count"],
            "peak_drift_psi": round(self._stats["max_psi"], 4),
        }
