from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

_LOG = logging.getLogger("qtrader.risk.anomaly_detector")


class AnomalyDetector:
    """
    Principal ML-based Anomaly Detection Engine.

    Objective: Identify abnormal behavior in strategies and system telemetry
    using a combination of low-latency statistical (Z-score) and
    advanced multivariate (Isolation Forest) models.
    """

    def __init__(
        self,
        z_threshold: float = 3.0,
        isolation_forest_contamination: float = 0.05,
        history_window: int = 500,
    ) -> None:
        """
        Initialize the Anomaly Detector with industrial defaults.

        Args:
            z_threshold: Sigma threshold for univariate anomaly detection.
            isolation_forest_contamination: Proportion of expected outliers.
            history_window: Sample size for moving-window modeling.
        """
        self._z_thresh = z_threshold
        self._iforest = IsolationForest(
            contamination=isolation_forest_contamination, random_state=42
        )
        self._history_window = history_window

        # History buffers for stateful modeling
        self._univariate_buffer: dict[str, list[float]] = {}
        self._multivariate_buffer: list[list[float]] = []

        # Telemetry
        self._stats = {"anomalies": 0, "evaluations": 0}

    def evaluate_univariate(self, key: str, value: float) -> dict[str, Any]:
        """
        Detect spikes in a single telemetry stream using Z-score logic.

        Process:
        1. Accumulate value in moving history window.
        2. Compute Z-score $(|x - \\mu| / \\sigma)$.
        3. Flag if deviation exceeds the institutional sigma threshold.

        Returns:
            dict containing anomaly status and statistical score.
        """
        self._stats["evaluations"] += 1

        if key not in self._univariate_buffer:
            self._univariate_buffer[key] = []

        buffer = self._univariate_buffer[key]
        buffer.append(value)

        # Skip detection if distribution is not yet stable (min 30 samples)
        if len(buffer) < 30:  # noqa: PLR2004
            return {"status": "WARM_UP", "anomaly": False, "key": key}

        # Maintain window size
        if len(buffer) > self._history_window:
            buffer.pop(0)

        # Compute stats on history (excluding the new point)
        mu = float(np.mean(buffer[:-1]))
        sigma = float(np.std(buffer[:-1]))

        # Safety epsilon for numerical stability
        if sigma < 1e-9:  # noqa: PLR2004
            return {"status": "STABLE", "anomaly": False, "key": key}

        z_score = abs(value - mu) / sigma
        is_anomaly = z_score > self._z_thresh

        if is_anomaly:
            self._stats["anomalies"] += 1
            _LOG.warning(f"[ANOMALY] {key} | Z-Score: {z_score:.2f} | T: {self._z_thresh}")

        return {
            "status": "ANALYSIS",
            "anomaly": is_anomaly,
            "score": round(z_score, 4),
            "key": key,
        }

    def evaluate_multivariate(self, vector: list[float]) -> dict[str, Any]:
        """
        Detect non-linear behavioral shifts using the Isolation Forest model.

        Process:
        1. Accumulate the high-dimensional vector in the history buffer.
        2. Re-fit/Predict using Isolation Forest to identify outliers.
        3. Compute normalized anomaly score for institutional monitoring.

        Returns:
            dict containing multivariate anomaly status and ML score.
        """
        start_time = time.perf_counter()
        self._stats["evaluations"] += 1

        self._multivariate_buffer.append(vector)
        # Maintenance Path: Ensure window size is capped
        if len(self._multivariate_buffer) > self._history_window:
            self._multivariate_buffer.pop(0)

        # Minimum data requirement for Isolation Forest (100 samples)
        if len(self._multivariate_buffer) < 100:  # noqa: PLR2004
            return {"status": "WARM_UP", "anomaly": False}

        # Re-fit and Predict (Online learning approximation)
        data = np.array(self._multivariate_buffer)
        self._iforest.fit(data)

        # -1 for anomaly, 1 for normal
        prediction = self._iforest.predict([vector])[0]
        # score_samples returns opposite of anomaly score (higher is more normal)
        raw_score = self._iforest.score_samples([vector])[0]

        is_anomaly = prediction == -1
        latency_ms = (time.perf_counter() - start_time) * 1000

        if is_anomaly:
            self._stats["anomalies"] += 1
            _LOG.warning(f"[ANOMALY] MULTIVARIATE | IForest Score: {raw_score:.4f}")

        return {
            "status": "ANALYSIS",
            "anomaly": is_anomaly,
            "score": round(float(abs(raw_score)), 4),
            "latency_ms": round(latency_ms, 4),
        }

    def get_anomaly_report(self) -> dict[str, Any]:
        """
        Generate ML-based risk summary report.
        """
        total = self._stats["evaluations"]
        return {
            "status": "ANOMALY_SUMMARY",
            "total_anomalies": self._stats["anomalies"],
            "anomaly_rate": (round(self._stats["anomalies"] / total, 4) if total > 0 else 0.0),
        }
