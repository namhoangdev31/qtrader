#!/usr/bin/env python3
"""Test script for DriftDetector."""

import numpy as np
import polars as pl
from analytics.drift_detector import DriftDetector

def test_drift_detector():
    """Test the drift detector functionality."""
    print("Testing DriftDetector...")
    
    # Create drift detector
    detector = DriftDetector(
        psi_warning_threshold=0.2,
        psi_critical_threshold=0.3,
        ks_pvalue_threshold=0.05
    )
    
    # Create reference data (normal distribution)
    np.random.seed(42)
    train_data = pl.DataFrame({
        'feature1': np.random.normal(0, 1, 1000),
        'feature2': np.random.normal(5, 2, 1000)
    })
    
    # Create live data with no drift
    live_data_no_drift = pl.DataFrame({
        'feature1': np.random.normal(0, 1, 1000),
        'feature2': np.random.normal(5, 2, 1000)
    })
    
    # Create live data with drift (shifted mean)
    live_data_with_drift = pl.DataFrame({
        'feature1': np.random.normal(2, 1, 1000),  # Shifted mean
        'feature2': np.random.normal(5, 2, 1000)
    })
    
    # Test with no drift
    result_no_drift = detector.detect_drift(train_data, live_data_no_drift, ['feature1', 'feature2'])
    print("No drift test:")
    print(f"  Drift alert: {result_no_drift['drift_alert']}")
    print(f"  Severity: {result_no_drift['severity']}")
    for col, metrics in result_no_drift['feature_drift'].items():
        print(f"  {col}: PSI={metrics['psi']:.4f}, KS p={metrics['ks_pvalue']:.4f}")
    
    # Test with drift
    result_with_drift = detector.detect_drift(train_data, live_data_with_drift, ['feature1', 'feature2'])
    print("\nWith drift test:")
    print(f"  Drift alert: {result_with_drift['drift_alert']}")
    print(f"  Severity: {result_with_drift['severity']}")
    for col, metrics in result_with_drift['feature_drift'].items():
        print(f"  {col}: PSI={metrics['psi']:.4f}, KS p={metrics['ks_pvalue']:.4f}")
    
    # Assertions
    assert not result_no_drift['drift_alert'], "Should not detect drift when there is none"
    assert result_with_drift['drift_alert'], "Should detect drift when there is drift"
    assert result_with_drift['severity'] in ['WARNING', 'CRITICAL', 'MEDIUM'], "Severity should indicate drift"
    assert result_with_drift['feature_drift']['feature1']['psi'] > 0.2, "PSI for feature1 should be > 0.2 with drift"
    
    print("\nAll tests passed!")

if __name__ == "__main__":
    test_drift_detector()