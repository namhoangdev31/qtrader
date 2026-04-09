from unittest.mock import MagicMock

import polars as pl
import pytest

from qtrader.ml.regime import RegimeDetector
from qtrader.ml.registry import ModelRegistry


def test_regime_detector_predict():
    detector = RegimeDetector(n_regimes=2)
    df = pl.DataFrame(
        {"momentum": [0.1, 0.2, 0.1, -0.1, -0.2], "mean_reversion": [0.05, 0.1, 0.0, -0.05, -0.1]}
    )

    detector.fit(df, ["momentum", "mean_reversion"])
    regimes = detector.predict_regime(df, ["momentum", "mean_reversion"])

    assert len(regimes) == 5
    assert regimes.dtype in [pl.Int32, pl.Int64, pl.Int8, pl.Int16]


def test_model_registry_get_best_model():
    from unittest.mock import MagicMock, patch

    # Mock search_runs return value as a pandas-like object
    mock_runs = MagicMock()
    mock_runs.empty = False
    mock_runs.iloc = [{"run_id": "test_run_id"}]

    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.search_runs", return_value=mock_runs),
    ):
        registry = ModelRegistry()
        run_id = registry.get_best_model("test_model")
        assert run_id == "test_run_id"

        # Test empty result
        mock_runs.empty = True
        assert registry.get_best_model("none") == ""


def test_model_registry_load_model():
    from unittest.mock import MagicMock, patch

    from qtrader.ml.registry import ModelRegistry

    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.pyfunc.load_model") as mock_load,
    ):
        mock_model = MagicMock()
        mock_load.return_value = mock_model

        registry = ModelRegistry()

        # Load by explicit run_id
        model = registry.load_model("test_run_id")
        # MLFlow URI structure for runs
        mock_load.assert_called_with("runs:/test_run_id/model")
        assert model == mock_model


def test_model_registry_prevent_stale_model():
    from unittest.mock import MagicMock, patch

    from qtrader.ml.registry import ModelRegistry

    # We test that the logic properly pulls the absolute latest if version isn't specified
    # Using our already-tested get_best_model mock
    mock_runs = MagicMock()
    mock_runs.empty = False
    mock_runs.iloc = [{"run_id": "latest_run_id"}]

    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.search_runs", return_value=mock_runs),
        patch("mlflow.pyfunc.load_model") as mock_load,
    ):
        registry = ModelRegistry()
        run_id = registry.get_best_model("my_model")
        registry.load_model(run_id)

        mock_load.assert_called_with("runs:/latest_run_id/model")
