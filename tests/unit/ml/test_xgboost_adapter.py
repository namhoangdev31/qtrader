import pytest
import numpy as np
from qtrader.ml.xgboost_adapter import XGBoostRiskAdapter, RiskClassificationResult

def test_xgboost_adapter_initialization():
    adapter = XGBoostRiskAdapter()
    assert adapter.model_id == "xgboost_v1"
    assert adapter._is_loaded is False

def test_xgboost_adapter_classify_format():
    adapter = XGBoostRiskAdapter()
    features = {f: 0.5 for f in adapter.DEFAULT_FEATURES}
    result = adapter.classify(features)
    
    assert isinstance(result, RiskClassificationResult)
    assert result.class_label in ["SAFE", "WARNING", "DANGER"]
    assert len(result.probabilities) == 3
    assert "SAFE" in result.probabilities
    assert result.inference_time_ms > 0

def test_xgboost_adapter_rule_logic():
    adapter = XGBoostRiskAdapter()
    # High risk features
    features = {"rsi": 90, "volatility": 0.1, "spread_bps": 50}
    result = adapter.classify(features)
    assert result.class_label == "DANGER"
    assert result.risk_score > 0.5

def test_xgboost_adapter_fit():
    adapter = XGBoostRiskAdapter()
    # Add enough data to trigger fit
    for _ in range(10):
        adapter.add_training_data({f: np.random.rand() for f in adapter.DEFAULT_FEATURES}, "SAFE")
    
    adapter.fit()
    assert adapter._is_loaded is True
    assert adapter._model is not None
