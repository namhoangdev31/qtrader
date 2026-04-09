from __future__ import annotations
import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)
try:
    import mlflow
    import mlflow.pyfunc
    import mlflow.tracking
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None
    MlflowClient = None
    MlflowException = Exception
T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class PromotionConfig:
    sharpe_threshold: float = 1.0
    drawdown_threshold: float = 0.1
    hit_rate_threshold: float = 0.5
    sharpe_improvement: float = 0.0
    drawdown_improvement: float = 0.0
    hit_rate_improvement: float = 0.0


class MLflowManager:
    def __init__(
        self,
        tracking_uri: str | None = None,
        experiment_name: str = "QTrader-Strategies",
        registry_uri: str | None = None,
        enable_mlflow: bool = True,
    ) -> None:
        self.enable_mlflow = enable_mlflow and MLFLOW_AVAILABLE
        self.experiment_name = experiment_name
        self.logger = logger
        if not self.enable_mlflow:
            if not MLFLOW_AVAILABLE:
                self.logger.warning(
                    "MLflow not installed. MLflow tracking disabled. Install mlflow to enable experiment tracking."
                )
            else:
                self.logger.info("MLflow tracking disabled by configuration.")
            self._client = None
            self._experiment_id = None
            return
        if tracking_uri is None:
            tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
        mlflow.set_tracking_uri(tracking_uri)
        self.tracking_uri = tracking_uri
        if registry_uri is None:
            registry_uri = os.getenv("MLFLOW_REGISTRY_URI", tracking_uri)
        self.registry_uri = registry_uri
        mlflow.set_registry_uri(registry_uri)
        try:
            self._client = MlflowClient()
            experiment = self._client.get_experiment_by_name(experiment_name)
            if experiment is None:
                self._experiment_id = self._client.create_experiment(experiment_name)
                self.logger.info(
                    f"Created MLflow experiment: {experiment_name} (ID: {self._experiment_id})"
                )
            else:
                self._experiment_id = experiment.experiment_id
                self.logger.info(
                    "Using existing MLflow experiment: %s (ID: %s)",
                    experiment_name,
                    self._experiment_id,
                )
        except Exception as e:
            self.logger.error(f"Failed to initialize MLflow: {e}")
            self.enable_mlflow = False
            self._client = None
            self._experiment_id = None

    async def log_run(
        self,
        strategy_name: str,
        parameters: dict[str, Any],
        metrics: dict[str, float],
        artifacts: dict[str, Any] | None = None,
        run_name: str | None = None,
    ) -> str | None:
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping run logging")
            return None
        loop = asyncio.get_event_loop()
        try:
            run_id = await loop.run_in_executor(
                None, self._log_run_sync, strategy_name, parameters, metrics, artifacts, run_name
            )
            return run_id
        except Exception as e:
            self.logger.error(f"Failed to log MLflow run: {e}")
            return None

    def _log_run_sync(
        self,
        strategy_name: str,
        parameters: dict[str, Any],
        metrics: dict[str, float],
        artifacts: dict[str, Any] | None = None,
        run_name: str | None = None,
    ) -> str:
        with mlflow.start_run(
            run_name=run_name or f"{strategy_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        ) as run:
            mlflow.log_params(parameters)
            mlflow.log_metrics(metrics)
            mlflow.set_tag("strategy_name", strategy_name)
            mlflow.set_tag("timestamp", datetime.utcnow().isoformat())
            if artifacts:
                with tempfile.TemporaryDirectory() as tmpdir:
                    for artifact_name, artifact_data in artifacts.items():
                        artifact_path = Path(tmpdir) / f"{artifact_name}.json"
                        with open(artifact_path, "w") as f:
                            json.dump(artifact_data, f, indent=2, default=str)
                    mlflow.log_artifacts(tmpdir, artifact_path="strategy_artifacts")
            run_id = run.info.run_id
            try:

                class DummyModel(mlflow.pyfunc.PythonModel):
                    def predict(self, context: Any, model_input: T) -> T:
                        return model_input

                mlflow.pyfunc.log_model(artifact_path="model", python_model=DummyModel())
            except Exception as e:
                self.logger.warning("Failed to log model: %s", e)
                with tempfile.TemporaryDirectory() as tmpdir:
                    model_path = Path(tmpdir) / "model.txt"
                    model_path.write_text(f"Dummy model for {strategy_name}")
                    mlflow.log_artifact(str(model_path), artifact_path="model")
            model_name = f"strategy_{strategy_name}"
            try:
                model_uri = f"runs:/{run_id}/model"
                model_version = mlflow.register_model(model_uri, model_name)
                client = self._client
                if client is not None:
                    client.transition_model_version_stage(
                        name=model_name,
                        version=model_version.version,
                        stage="Staging",
                        archive_existing_versions=False,
                    )
                else:
                    self.logger.warning("MLflow client not available for staging transition")
                self.logger.info(
                    "Registered model %s version %s in Staging", model_name, model_version.version
                )
            except Exception as e:
                self.logger.error(f"Failed to register model {model_name}: {e}")
            return run_id

    async def evaluate_and_promote(
        self,
        strategy_name: str,
        run_id: str,
        sharpe_threshold: float = 1.0,
        drawdown_threshold: float = 0.1,
        hit_rate_threshold: float = 0.5,
    ) -> bool:
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping promotion")
            return False
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._evaluate_and_promote_sync,
                strategy_name,
                run_id,
                sharpe_threshold,
                drawdown_threshold,
                hit_rate_threshold,
            )
            return result
        except Exception as e:
            self.logger.error(f"Failed to evaluate and promote: {e}")
            return False

    def _evaluate_and_promote_sync(
        self,
        strategy_name: str,
        run_id: str,
        sharpe_threshold: float,
        drawdown_threshold: float,
        hit_rate_threshold: float,
    ) -> bool:
        try:
            run = self._client.get_run(run_id)
            metrics = run.data.metrics
            sharpe = metrics.get("sharpe_ratio", 0.0)
            drawdown = metrics.get("max_drawdown", 1.0)
            hit_rate = metrics.get("hit_rate", 0.0)
            self.logger.info(
                f"Evaluating strategy {strategy_name} (run {run_id}): Sharpe={sharpe:.3f} (>{sharpe_threshold}), Drawdown={drawdown:.3f} (<{drawdown_threshold}), Hit Rate={hit_rate:.3f} (>{hit_rate_threshold})"
            )
            if (
                sharpe > sharpe_threshold
                and drawdown < drawdown_threshold
                and (hit_rate > hit_rate_threshold)
            ):
                model_name = f"strategy_{strategy_name}"
                client = self._client
                if client is None:
                    raise RuntimeError("MLflow client not initialized")
                latest_versions = client.get_latest_versions(model_name, stages=["Staging"])
                if not latest_versions:
                    self.logger.warning(f"No staging version found for {model_name}")
                    return False
                version = latest_versions[0].version
                client.transition_model_version_stage(
                    name=model_name,
                    version=version,
                    stage="Production",
                    archive_existing_versions=True,
                )
                self.logger.info("Promoted %s version %s to Production", model_name, version)
                return True
            else:
                self.logger.info(
                    f"Strategy {strategy_name} did not meet promotion criteria. Keeping in Staging or failing."
                )
                return False
        except Exception as e:
            self.logger.error(f"Error during evaluation and promotion: {e}")
            return False

    async def promote_if_better_than_production(
        self, strategy_name: str, shadow_run_id: str, config: PromotionConfig | None = None
    ) -> bool:
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping promotion")
            return False
        loop = asyncio.get_event_loop()
        try:
            result: bool = await loop.run_in_executor(
                None,
                self._promote_if_better_than_production_sync,
                strategy_name,
                shadow_run_id,
                config,
            )
            return result
        except Exception as e:
            self.logger.error(f"Failed to promote if better than production: {e}")
            return False

    def _promote_if_better_than_production_sync(
        self, strategy_name: str, shadow_run_id: str, cfg: PromotionConfig
    ) -> bool:
        client = self._client
        if client is None:
            raise RuntimeError("MLflow client not initialized")
        try:
            shadow_run = client.get_run(shadow_run_id)
            shadow_metrics = shadow_run.data.metrics
            sharpe = shadow_metrics.get("sharpe_ratio", 0.0)
            drawdown = shadow_metrics.get("max_drawdown", 1.0)
            hit_rate = shadow_metrics.get("hit_rate", 0.0)
            self.logger.info(
                f"Evaluating shadow strategy {strategy_name} (run {shadow_run_id}): Sharpe={sharpe:.3f} (>{cfg.sharpe_threshold}), Drawdown={drawdown:.3f} (<{cfg.drawdown_threshold}), Hit Rate={hit_rate:.3f} (>{cfg.hit_rate_threshold})"
            )
            if not (
                sharpe > cfg.sharpe_threshold
                and drawdown < cfg.drawdown_threshold
                and (hit_rate > cfg.hit_rate_threshold)
            ):
                self.logger.info(
                    "Shadow strategy %s failed absolute criteria (Sharpe=%.2f, DD=%.2f)",
                    strategy_name,
                    sharpe,
                    drawdown,
                )
                return False
            model_name = f"strategy_{strategy_name}"
            prod_versions = client.get_latest_versions(model_name, stages=["Production"])
            if not prod_versions:
                self.logger.info(
                    f"No production version found for {model_name}. Promoting based on absolute thresholds only."
                )
                staging_versions = client.get_latest_versions(model_name, stages=["Staging"])
                if not staging_versions:
                    self.logger.warning(f"No staging version found for {model_name} to promote")
                    return False
                version = staging_versions[0].version
                client.transition_model_version_stage(
                    name=model_name,
                    version=version,
                    stage="Production",
                    archive_existing_versions=False,
                )
                self.logger.info(
                    "Promoted %s v%s from run %s to Production (first version)",
                    model_name,
                    version,
                    shadow_run_id,
                )
                return True
            prod_version = prod_versions[0]
            prod_run_id = prod_version.run_id
            prod_run = client.get_run(prod_run_id)
            prod_metrics = prod_run.data.metrics
            prod_sharpe = prod_metrics.get("sharpe_ratio", 0.0)
            prod_drawdown = prod_metrics.get("max_drawdown", 1.0)
            prod_hit_rate = prod_metrics.get("hit_rate", 0.0)
            self.logger.info(
                "Production model %s v%s: Sharpe=%.3f",
                model_name,
                prod_version.version,
                prod_sharpe,
            )
            sharpe_improvement = sharpe - prod_sharpe
            drawdown_improvement = prod_drawdown - drawdown
            hit_rate_improvement = hit_rate - prod_hit_rate
            if (
                sharpe_improvement > cfg.sharpe_improvement
                and drawdown_improvement > cfg.drawdown_improvement
                and (hit_rate_improvement > cfg.hit_rate_improvement)
            ):
                self.logger.info(
                    "Shadow strategy %s is better than production (Sharpe +%.3f)",
                    strategy_name,
                    sharpe_improvement,
                )
                staging_versions = client.get_latest_versions(model_name, stages=["Staging"])
                if not staging_versions:
                    self.logger.warning("No staging version found for %s to promote", model_name)
                    return False
                version = staging_versions[0].version
                client.transition_model_version_stage(
                    name=model_name,
                    version=version,
                    stage="Production",
                    archive_existing_versions=True,
                )
                self.logger.info(
                    f"Promoted {model_name} version {version} from shadow run {shadow_run_id} to Production, archived version {prod_version.version}"
                )
                return True
            else:
                self.logger.info("Shadow strategy %s is not better than production", strategy_name)
                return False
        except Exception as e:
            self.logger.error(f"Error during evaluation and promotion: {e}")
            return False

    async def rollback_to_previous_production(self, strategy_name: str) -> bool:
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping rollback")
            return False
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self._rollback_to_previous_production_sync, strategy_name
            )
            return result
        except Exception as e:
            self.logger.error(f"Failed to rollback: {e}")
            return False

    def _rollback_to_previous_production_sync(self, strategy_name: str) -> bool:
        client = self._client
        if client is None:
            raise RuntimeError("MLflow client not initialized")
        try:
            model_name = f"strategy_{strategy_name}"
            prod_versions = client.get_latest_versions(model_name, stages=["Production"])
            if not prod_versions:
                self.logger.warning(f"No production version found for {model_name}")
                return False
            current_prod_version = prod_versions[0].version
            archived_versions = client.get_latest_versions(model_name, stages=["Archived"])
            if not archived_versions:
                self.logger.warning(f"No archived version found for {model_name} to rollback to")
                return False
            archived_versions_sorted = sorted(
                archived_versions, key=lambda v: int(v.version), reverse=True
            )
            previous_version = archived_versions_sorted[0].version
            client.transition_model_version_stage(
                name=model_name,
                version=current_prod_version,
                stage="Archived",
                archive_existing_versions=False,
            )
            client.transition_model_version_stage(
                name=model_name,
                version=previous_version,
                stage="Production",
                archive_existing_versions=True,
            )
            self.logger.info(
                "Rolled back %s from version %s to %s",
                model_name,
                current_prod_version,
                previous_version,
            )
            return True
        except Exception as e:
            self.logger.error(f"Error during rollback: {e}")
            return False

    async def load_production_model(self, strategy_name: str) -> Any | None:
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping model load")
            return None
        loop = asyncio.get_event_loop()
        try:
            model = await loop.run_in_executor(
                None, self._load_production_model_sync, strategy_name
            )
            return model
        except Exception as e:
            self.logger.error(f"Failed to load production model: {e}")
            return None

    def _load_production_model_sync(self, strategy_name: str) -> Any | None:
        client = self._client
        if client is None:
            raise RuntimeError("MLflow client not initialized")
        try:
            model_name = f"strategy_{strategy_name}"
            prod_versions = client.get_latest_versions(model_name, stages=["Production"])
            if not prod_versions:
                self.logger.warning(f"No production version found for {model_name}")
                return None
            version = prod_versions[0].version
            model_uri = f"models:/{model_name}/{version}"
            self.logger.info("Loading model %s version %s from %s", model_name, version, model_uri)
            return model_uri
        except Exception as e:
            self.logger.error(f"Error loading production model: {e}")
            return None

    def get_model_status(self, strategy_name: str) -> dict[str, Any]:
        if not self.enable_mlflow:
            return {"error": "MLflow disabled"}
        try:
            model_name = f"strategy_{strategy_name}"
            stages = ["None", "Staging", "Production", "Archived"]
            client = self._client
            if client is None:
                raise RuntimeError("MLflow client not initialized")
            status = {}
            for stage in stages:
                versions = client.get_latest_versions(model_name, stages=[stage])
                if versions:
                    status[stage.lower()] = {
                        "version": versions[0].version,
                        "run_id": versions[0].run_id,
                        "current_stage": versions[0].current_stage,
                    }
                else:
                    status[stage.lower()] = None
            return status
        except Exception as e:
            self.logger.error(f"Error getting model status: {e}")
            return {"error": str(e)}

    def is_enabled(self) -> bool:
        return self.enable_mlflow
