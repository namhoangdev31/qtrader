import mlflow
import polars as pl
from typing import Dict, Any, List, Optional
import json

class ModelRegistry:
    """Wrapper for MLflow to handle systematic model versioning and metadata."""
    
    def __init__(self, experiment_name: str = "QTrader_v3") -> None:
        mlflow.set_experiment(experiment_name)

    def log_model_iteration(
        self, 
        model_name: str,
        model: Any, 
        features: List[str],
        params: Dict[str, Any],
        metrics: Dict[str, float],
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """Logs a training iteration with hyperparams, features, and metrics."""
        with mlflow.start_run(run_name=model_name) as run:
            # 1. Log parameters and features
            mlflow.log_params(params)
            mlflow.log_dict({"features": features}, "features.json")
            
            # 2. Log metrics
            mlflow.log_metrics(metrics)
            
            # 3. Log tags (e.g., symbols, timeframe)
            if tags:
                mlflow.set_tags(tags)
            
            # 4. Save model artifact (assuming sklearn/xgb/catboost/pytorch-like interface)
            # This is a generic placeholder; in practice, use mlflow.sklearn.log_model, etc.
            mlflow.log_text(f"Placeholder for {type(model)} structure", "model_summary.txt")
            
            return run.info.run_id

    def get_best_model(self, model_name: str, metric: str = "mse") -> str:
        """Retrieves the run ID of the best performing model."""
        runs = mlflow.search_runs(
            experiment_names=["QTrader_v3"],
            filter_string=f"tags.mlflow.runName = '{model_name}'",
            order_by=[f"metrics.{metric} ASC"]
        )
        if not runs.empty:
            return runs.iloc[0]["run_id"]
        return ""
