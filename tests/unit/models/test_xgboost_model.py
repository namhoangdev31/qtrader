import pytest
from unittest.mock import MagicMock
from qtrader.models.xgboost_model import XGBoostModel

def test_xgboost_model_initialization():
    model = XGBoostModel(n_estimators=100, max_depth=3)
    assert model.n_estimators == 100
    assert model.max_depth == 3

def test_xgboost_model_fit():
    model = XGBoostModel()
    mock_X = MagicMock()
    mock_y = MagicMock()
    
    # Should not raise
    model.fit(mock_X, mock_y)

def test_xgboost_model_predict():
    model = XGBoostModel()
    mock_X = MagicMock()
    # Mock trained state
    model.is_trained = True
    model.model = MagicMock()
    model.model.predict.return_value = [1.0, 0.0]
    
    preds = model.predict(mock_X)
    assert len(preds) == 2
    assert preds[0] == 1.0

def test_xgboost_model_predict_untrained():
    model = XGBoostModel()
    mock_X = MagicMock()
    with pytest.raises(RuntimeError):
        model.predict(mock_X)
