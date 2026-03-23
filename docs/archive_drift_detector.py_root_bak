"""Drift detector for monitoring data and model drift using PSI and KS-Test."""
from __future__ import annotations

import logging
import numpy as np
import polars as pl
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

class DriftDetector:
    """
    Detects drifts in feature distributions and model predictions
    using Population Stability Index (PSI) and Kolmogorov-Smirnov (KS) test.
    """

    def __init__(
        self,
        psi_warning_threshold: float = 0.2,
        psi_critical_threshold: float = 0.3,
        ks_pvalue_threshold: float = 0.05
    ) -> None:
        """
        Initialize drift detector.

        Args:
            psi_warning_threshold: PSI threshold for warning level
            psi_critical_threshold: PSI threshold for critical level
            ks_pvalue_threshold: KS test p-value threshold for drift detection
        """
        self.psi_warning_threshold = psi_warning_threshold
        self.psi_critical_threshold = psi_critical_threshold
        self.ks_pvalue_threshold = ks_pvalue_threshold

    @staticmethod
    def calculate_psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
        """
        Calculates Population Stability Index (PSI).

        Args:
            expected: Expected distribution (e.g., from training data)
            actual: Actual distribution (e.g., from live data)
            buckets: Number of buckets for histogram

        Returns:
            PSI value
        """
        def get_counts(arr: np.ndarray, bins: np.ndarray) -> np.ndarray:
            return np.histogram(arr, bins=bins)[0]

        # Handle edge case where all values are the same
        if len(expected) == 0 or len(actual) == 0:
            return 0.0

        # Create buckets based on the range of both distributions
        min_val = min(expected.min(), actual.min())
        max_val = max(expected.max(), actual.max())
        
        # Avoid division by zero if all values are identical
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

    def _ks_2samp(self, data1: np.ndarray, data2: np.ndarray) -> Tuple[float, float]:
        """
        Computes the Kolmogorov-Smirnov statistic and p-value for two samples.
        Implementation without scipy.

        Args:
            data1: First sample
            data2: Second sample

        Returns:
            Tuple of (KS statistic, p-value)
        """
        # Convert to numpy arrays
        data1 = np.asarray(data1)
        data2 = np.asarray(data2)
        n1 = len(data1)
        n2 = len(data2)
        
        if n1 == 0 or n2 == 0:
            return 0.0, 1.0

        # Sort data1 and data2
        data1_sorted = np.sort(data1)
        data2_sorted = np.sort(data2)
        
        # Get all unique values from both datasets
        all_values = np.concatenate([data1_sorted, data2_sorted])
        all_values = np.sort(np.unique(all_values))
        
        if len(all_values) < 2:
            # If all values are the same, KS statistic is 0
            return 0.0, 1.0
        
        # Calculate ECDF for each dataset at all values
        # Using searchsorted to find how many values are <= each point
        cdf1 = np.searchsorted(data1_sorted, all_values, side='right') / n1
        cdf2 = np.searchsorted(data2_sorted, all_values, side='right') / n2
        
        # The KS statistic is the maximum absolute difference between the two ECDFs
        d = np.max(np.abs(cdf1 - cdf2))
        
        # Compute p-value using asymptotic approximation for two-sample KS test
        # Formula: p = 2 * exp(-2 * (statistic^2)) where statistic = sqrt(n_eff) * d
        # and n_eff = n1 * n2 / (n1 + n2)
        en = np.sqrt(n1 * n2 / (n1 + n2))
        statistic = en * d
        
        # For small samples, we'd use exact distribution, but for larger samples (>35 each)
        # the asymptotic approximation is good
        # Using the asymptotic formula: p = 2 * sum_{k=1}^{∞} (-1)^{k-1} * exp(-2 * k^2 * statistic^2)
        if statistic == 0:
            p = 1.0
        else:
            # Use asymptotic approximation
            # This series converges quickly
            p = 0.0
            for k in range(1, 50):  # Enough terms for convergence
                term = ((-1) ** (k - 1)) * np.exp(-2 * (k ** 2) * (statistic ** 2))
                p += term
                # Break early if term is very small
                if abs(term) < 1e-10:
                    break
            p = 2 * p
            # Ensure p is in [0, 1]
            p = max(0.0, min(1.0, p))
        
        return d, p

    def detect_drift(self, train_data: pl.DataFrame, live_data: pl.DataFrame, columns: List[str]) -> Dict[str, Any]:
        """
        Detects drift between training and live data for specified columns.

        Args:
            train_data: Training/reference data
            live_data: Live/production data
            columns: List of column names to check for drift

        Returns:
            Dictionary containing:
                - feature_drift: dict mapping column name to drift metrics
                - drift_alert: boolean indicating if drift was detected
                - severity: string indicating drift severity (LOW, MEDIUM, WARNING, CRITICAL)
        """
        from qtrader.core.logger import StructuredLogger
        logger = StructuredLogger("drift_detector")
        
        feature_drift = {}
        drift_detected = False
        max_severity = "LOW"  # LOW < MEDIUM < WARNING < CRITICAL
        
        for col in columns:
            if col not in train_data.columns or col not in live_data.columns:
                logger.warning(f"Column {col} not found in both datasets, skipping")
                continue
                
            # Extract column data as numpy arrays
            train_col = train_data[col].to_numpy()
            live_col = live_data[col].to_numpy()
            
            # Calculate PSI
            psi = self.calculate_psi(train_col, live_col)
            
            # Calculate KS test
            ks_statistic, ks_pvalue = self._ks_2samp(train_col, live_col)
            
            # Store results for this feature
            feature_drift[col] = {
                "psi": float(psi),
                "ks_statistic": float(ks_statistic),
                "ks_pvalue": float(ks_pvalue)
            }
            
            # Check for drift and update severity
            feature_drift_detected = False
            if psi > self.psi_critical_threshold:
                feature_drift_detected = True
                severity = "CRITICAL"
            elif psi > self.psi_warning_threshold:
                feature_drift_detected = True
                severity = "WARNING"
            elif ks_pvalue < self.ks_pvalue_threshold:
                feature_drift_detected = True
                severity = "MEDIUM"
            else:
                severity = "LOW"
                
            if feature_drift_detected:
                drift_detected = True
                
            # Update overall severity (take the highest)
            severity_order = {"LOW": 0, "MEDIUM": 1, "WARNING": 2, "CRITICAL": 3}
            if severity_order[severity] > severity_order[max_severity]:
                max_severity = severity
                
            logger.debug(
                f"Drift check for {col}: PSI={psi:.4f}, KS_stat={ks_statistic:.4f}, "
                f"KS_p={ks_pvalue:.4f}, severity={severity}"
            )
        
        result = {
            "feature_drift": feature_drift,
            "drift_alert": drift_detected,
            "severity": max_severity
        }
        
        logger.info(
            f"Drift detection complete: alert={drift_detected}, severity={max_severity}, "
            f"features_checked={len(columns)}"
        )
        
        return result