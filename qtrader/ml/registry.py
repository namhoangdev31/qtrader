import hashlib
import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

try:
    import mlflow
    import mlflow.pyfunc

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None
from qtrader.core.config import Config


class ModelRegistry:
    def __init__(self, experiment_name: str | None = None, tracking_uri: str | None = None) -> None:
        try:
            uri = tracking_uri if tracking_uri is not None else Config.MLFLOW_URI
            mlflow.set_tracking_uri(uri)
            exp = experiment_name or os.getenv("MLFLOW_EXPERIMENT_NAME", "qtrader_v4_autonomous")
            mlflow.set_experiment(exp)
        except Exception as exc:
            raise RuntimeError(f"MLflow initialization failed: {exc}") from exc
        self.experiment_name = exp

    def log_model_iteration(
        self,
        model_name: str,
        model: Any,
        features: list[str],
        params: dict[str, Any],
        metrics: dict[str, float],
        tags: dict[str, str] | None = None,
        artifact_path: str = "model",
        register_model_name: str | None = None,
    ) -> str:
        with mlflow.start_run(run_name=model_name) as run:
            mlflow.log_params(params)
            mlflow.log_dict({"features": features}, "features.json")
            mlflow.log_metrics(metrics)
            if tags:
                mlflow.set_tags(tags)
            params_hash = hashlib.sha256(
                json.dumps(params, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            mlflow.set_tags(
                {
                    "model_type": str(type(model)),
                    "params_hash": params_hash,
                    "trained_at": datetime.now(ZoneInfo(Config.timezone)).isoformat(),
                }
            )
            try:
                module_name = type(model).__module__
                if module_name.startswith("sklearn"):
                    mlflow.sklearn.log_model(
                        model,
                        artifact_path=artifact_path,
                        registered_model_name=register_model_name,
                    )
                elif module_name.startswith("xgboost"):
                    mlflow.xgboost.log_model(
                        model,
                        artifact_path=artifact_path,
                        registered_model_name=register_model_name,
                    )
                elif module_name.startswith("catboost"):
                    mlflow.catboost.log_model(
                        model,
                        artifact_path=artifact_path,
                        registered_model_name=register_model_name,
                    )
                elif module_name.startswith("lightgbm"):
                    mlflow.lightgbm.log_model(
                        model,
                        artifact_path=artifact_path,
                        registered_model_name=register_model_name,
                    )
                else:
                    mlflow.log_text(
                        f"Model type: {type(model)}", f"{artifact_path}/model_summary.txt"
                    )
            except Exception:
                mlflow.log_text(
                    f"Model logging failed for {type(model)}", f"{artifact_path}/model_summary.txt"
                )
            return str(run.info.run_id)

    def get_best_model(self, model_name: str, metric: str = "mse") -> str:
        runs = mlflow.search_runs(
            experiment_names=[self.experiment_name],
            filter_string=f"tags.mlflow.runName = '{model_name}'",
            order_by=[f"metrics.{metric} ASC"],
        )
        if hasattr(runs, "empty") and (not runs.empty):
            return str(runs.iloc[0]["run_id"])
        if isinstance(runs, list) and len(runs) > 0:
            rid = runs[0].info.run_id if hasattr(runs[0], "info") else runs[0].get("run_id", "")
            return str(rid)
        return ""

    def load_model(self, run_id: str) -> Any:
        if not MLFLOW_AVAILABLE:
            raise RuntimeError("MLflow is not available.")
        model_uri = f"runs:/{run_id}/model"
        return mlflow.pyfunc.load_model(model_uri)
