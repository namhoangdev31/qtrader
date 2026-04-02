from unittest.mock import MagicMock

import numpy as np
import pytest

from qtrader.ml.model_comparator import ComparisonResult, ModelComparator


@pytest.fixture
def comparator() -> ModelComparator:
    """Initialize ModelComparator with industrial defaults."""
    return ModelComparator(alpha=0.05, sharpe_safety_buffer=0.05)


def test_comparison_significance_promotion(comparator: ModelComparator) -> None:
    """Verify that a significantly better model (lower MSE) is promoted."""
    x_val = np.random.randn(100, 5)
    y_val = np.random.randn(100)
    
    # Model Old: Random noise (High MSE)
    old_model = MagicMock()
    # Residuals ~ 1.0 variance
    old_model.predict.return_value = y_val + np.random.normal(0, 1.0, 100)
    
    # Model New: Better fit (Lower MSE)
    new_model = MagicMock()
    # Residuals ~ 0.5 variance
    new_model.predict.return_value = y_val + np.random.normal(0, 0.5, 100)
    
    result = comparator.compare(old_model, new_model, x_val, y_val)
    assert result.decision == "PROMOTE"
    assert result.is_statistically_significant is True
    assert result.mse_delta > 0


def test_comparison_not_significant_rejection(comparator: ModelComparator) -> None:
    """Verify that models with marginal/insignificant improvement are rejected."""
    x_val = np.random.randn(100, 5)
    y_val = np.random.randn(100)
    
    # Two identical models (identical predictions)
    old_model = MagicMock()
    preds = y_val + np.random.normal(0, 0.1, 100)
    old_model.predict.return_value = preds
    
    new_model = MagicMock()
    new_model.predict.return_value = preds + np.random.normal(0, 0.001, 100) # Negligible noise
    
    result = comparator.compare(old_model, new_model, x_val, y_val)
    assert result.decision == "REJECT"
    assert result.is_statistically_significant is False


def test_comparison_sharpe_degradation_rejection(comparator: ModelComparator) -> None:
    """Verify that models with Sharpe degradation (> 5%) are rejected."""
    x_val = np.random.randn(100, 5)
    y_val = np.random.randn(100)
    
    # Model Old: Baseline
    old_model = MagicMock()
    # Predictions: Positive mean (high sharpe)
    old_model.predict.return_value = np.ones(100) * 0.1 + np.random.normal(0, 0.01, 100)
    
    # Model New: Lower MSE but Zero Mean (low sharpe)
    # Even if MSE is lower, Sharpe degradation should trigger REJECT
    new_model = MagicMock()
    new_model.predict.return_value = np.random.normal(0, 0.001, 100) # Near Zero Error, but zero Sharpe
    
    # Trick: Set y_val to be the same as new_model.predict to force near-zero MSE
    target_y = new_model.predict.return_value
    
    result = comparator.compare(old_model, new_model, x_val, target_y)
    
    # It will be statistically significant for MSE (since new matches Y perfectly)
    assert result.is_statistically_significant is True
    # But Sharpe degraded drastically (Old: high, New: 0)
    assert result.decision == "REJECT"


def test_comparison_telemetry(comparator: ModelComparator) -> None:
    """Verify situational awareness report tracking."""
    x_val = np.zeros((10, 5))
    y_val = np.zeros(10)
    
    m = MagicMock()
    m.predict.return_value = np.zeros(10)
    
    # 1. Identical comparison (Reject)
    comparator.compare(m, m, x_val, y_val)
    
    report = comparator.get_comparison_report()
    assert report["total_comparisons"] == 1
    assert report["promotion_rate"] == 0.0
