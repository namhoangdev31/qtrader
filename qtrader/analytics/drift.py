
import numpy as np
import polars as pl
from scipy.stats import ks_2samp


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
            
        bins = np.linspace(
            min(expected.min(), actual.min()),
            max(expected.max(), actual.max()),
            buckets + 1,
        )
        expected_counts = get_counts(expected, bins) / len(expected)
        actual_counts = get_counts(actual, bins) / len(actual)
        
        # Add small epsilon to avoid log(0)
        expected_counts = np.clip(expected_counts, 1e-6, None)
        actual_counts = np.clip(actual_counts, 1e-6, None)
        
        psi = np.sum((actual_counts - expected_counts) * np.log(actual_counts / expected_counts))
        return psi

    @staticmethod
    def detect_drift(train_data: pl.DataFrame, live_data: pl.DataFrame, columns: list[str]) -> dict[str, float]:
        """Detects drift using Kolmogorov-Smirnov test."""
        drifts = {}
        for col in columns:
            if col in train_data.columns and col in live_data.columns:
                _stat, p_value = ks_2samp(
                    train_data[col].to_numpy(),
                    live_data[col].to_numpy(),
                )
                drifts[col] = p_value # Low p-value indicates drift
        return drifts
