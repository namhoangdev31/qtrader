from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
import numpy as np

_LOG = logging.getLogger("qtrader.ml.retrain_system")


@dataclass(slots=True, frozen=True)
class RetrainDecision:
    trigger: bool
    psi: float
    performance_drop: float
    reason: str


class RetrainSystem:
    def __init__(self, psi_threshold: float = 0.25, performance_drop_delta: float = 0.15) -> None:
        self._psi_threshold = psi_threshold
        self._delta = performance_drop_delta
        self._stats = {"retrain_count": 0, "max_psi": 0.0}

    def compute_psi(self, expected: np.ndarray[Any, Any], actual: np.ndarray[Any, Any]) -> float:
        sum_p = np.sum(expected)
        sum_q = np.sum(actual)
        p = expected / sum_p if sum_p > 0 else expected
        q = actual / sum_q if sum_q > 0 else actual
        eps = 1e-06
        p = np.clip(p, eps, 1.0)
        q = np.clip(q, eps, 1.0)
        psi_values = (p - q) * np.log(p / q)
        return float(np.sum(psi_values))

    def evaluate(
        self,
        expected_dist: np.ndarray[Any, Any],
        actual_dist: np.ndarray[Any, Any],
        current_perf: float,
        baseline_perf: float,
    ) -> RetrainDecision:
        psi = self.compute_psi(expected_dist, actual_dist)
        perf_drop = max(0.0, baseline_perf - current_perf)
        trigger = False
        reason = "NOMINAL_OPERATING_CONDITIONS"
        if psi > self._psi_threshold:
            trigger = True
            reason = f"SIGNIFICANT_DATA_DRIFT_IDENTIFIED: PSI={psi:.4f}"
        elif perf_drop > self._delta:
            trigger = True
            reason = f"PERFORMANCE_DECAY_DETECTED: Drop={perf_drop:.4f}"
        if trigger:
            self._stats["retrain_count"] += 1
            _LOG.warning(f"[RETRAIN] {reason}")
        self._stats["max_psi"] = max(self._stats["max_psi"], psi)
        return RetrainDecision(
            trigger=trigger, psi=round(psi, 4), performance_drop=round(perf_drop, 4), reason=reason
        )

    def get_retrain_report(self) -> dict[str, Any]:
        return {
            "status": "RETRAIN_REPORT",
            "total_triggers": self._stats["retrain_count"],
            "peak_drift_psi": round(self._stats["max_psi"], 4),
        }
