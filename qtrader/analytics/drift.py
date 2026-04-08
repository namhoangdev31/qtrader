"""Standardized Drift Monitoring for QTrader."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
from scipy.stats import ks_2samp

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)


class DriftMonitor:
    """
    Detects drifts in model predictions and feature distributions
    to identify alpha decay.
    """
    
    @staticmethod
    def calculate_psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
        """Calculates Population Stability Index (PSI)."""
        def get_counts(arr: np.ndarray, bins: np.ndarray) -> np.ndarray:
            return np.histogram(arr, bins=bins)[0]
            
        # Handle edge case where all values are the same
        if len(expected) == 0 or len(actual) == 0:
            return 0.0

        min_val = min(expected.min(), actual.min())
        max_val = max(expected.max(), actual.max())
        
        if min_val == max_val:
            return 0.0

        bins = np.linspace(min_val, max_val, buckets + 1)
        expected_counts = get_counts(expected, bins) / len(expected)
        actual_counts = get_counts(actual, bins) / len(actual)
        
        # Add small epsilon to avoid log(0)
        epsilon = 1e-10
        expected_counts = np.clip(expected_counts, epsilon, None)
        actual_counts = np.clip(actual_counts, epsilon, None)
        
        psi = np.sum((actual_counts - expected_counts) * np.log(actual_counts / expected_counts))
        return psi

    @staticmethod
    def detect_drift(train_data: pl.DataFrame, live_data: pl.DataFrame, columns: list[str]) -> dict[str, Any]:
        """
        Detects drift using Kolmogorov-Smirnov test and PSI.
        
        Returns:
            Dictionary containing feature drift metrics and alert status.
        """
        feature_drift = {}
        drift_detected = False
        max_severity = "LOW"
        psi_warning = 0.2
        psi_critical = 0.3
        
        for col in columns:
            if col in train_data.columns and col in live_data.columns:
                train_col = train_data[col].to_numpy()
                live_col = live_data[col].to_numpy()
                
                # PSI
                psi = DriftMonitor.calculate_psi(train_col, live_col)
                
                # KS Test (using scipy)
                _stat, p_value = ks_2samp(train_col, live_col)
                
                feature_drift[col] = {
                    "psi": float(psi),
                    "ks_pvalue": float(p_value)
                }
                
                # Severity Logic
                if psi > psi_critical:
                    severity = "CRITICAL"
                    drift_detected = True
                elif psi > psi_warning:
                    severity = "WARNING"
                    drift_detected = True
                elif p_value < 0.05:
                    severity = "MEDIUM"
                    drift_detected = True
                else:
                    severity = "LOW"
                
                severity_order = {"LOW": 0, "MEDIUM": 1, "WARNING": 2, "CRITICAL": 3}
                if severity_order[severity] > severity_order[max_severity]:
                    max_severity = severity
                    
        return {
            "feature_drift": feature_drift,
            "drift_alert": drift_detected,
            "severity": max_severity
        }
