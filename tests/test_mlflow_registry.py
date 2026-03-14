from pathlib import Path

from qtrader.ml.registry import ModelRegistry


def test_mlflow_registry_fallback_logging(tmp_path: Path) -> None:
    # Use a local file-based tracking URI to avoid network dependency.
    registry = ModelRegistry(
        experiment_name="test_exp",
        tracking_uri=f"file:{tmp_path}/mlruns",
    )

    model = object()
    run_id = registry.log_model_iteration(
        model_name="dummy",
        model=model,
        features=["f1", "f2"],
        params={"a": 1},
        metrics={"mse": 0.1},
    )
    assert isinstance(run_id, str) and len(run_id) > 0
