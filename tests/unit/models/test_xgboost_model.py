from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest

from qtrader.models.xgboost_model import XGBoostPredictor


def test_xgboost_model_initialization():
    model = XGBoostPredictor(model_params={"n_estimators": 100})
    assert model.model.n_estimators == 100

def test_xgboost_model_train():
    model = XGBoostPredictor()
    mock_X = pl.DataFrame({"f1": [1.0, 2.0]})
    mock_y = pl.Series("target", [3.0, 4.0])
    
    model.train(mock_X, mock_y)
    # Success if no error call to fit inside

def test_xgboost_model_predict():
    model = XGBoostPredictor()
    mock_X = pl.DataFrame({"f1": [1.0]})
    # Mocking underlying model predict
    model.model.predict = MagicMock(return_value=np.array([1.0]))
    
    preds = model.predict(mock_X)
    assert len(preds) == 1
    assert preds[0] == 1.0
