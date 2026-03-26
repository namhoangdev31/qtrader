"""MLflow integration for QTrader MLOps platform.

This module provides MLflow tracking capabilities for strategy experiments,
model versioning, and production promotion/rollback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import MLflow, but don't fail if not available
try:
    import mlflow
    import mlflow.tracking
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None  # type: ignore
    MlflowClient = None  # type: ignore
    MlflowException = Exception  # type: ignore


class MLflowManager:
    """Manages MLflow tracking for QTrader strategies and models.

    Features:
    - Experiment tracking for strategy versions
    - Model registry with staging/production/archived stages
    - Automatic promotion based on performance thresholds
    - Rollback capabilities
    - Async-safe operations (runs MLflow calls in thread pool)
    """

    def __init__(
        self,
        tracking_uri: str | None = None,
        experiment_name: str = "QTrader-Strategies",
        registry_uri: str | None = None,
        enable_mlflow: bool = True,
    ) -> None:
        """Initialize MLflow manager.

        Args:
            tracking_uri: MLflow tracking server URI (defaults to MLFLOW_TRACKING_URI env or local)
            experiment_name: Name of the experiment for strategy tracking
            registry_uri: MLflow model registry URI (defaults to tracking_uri if not set)
            enable_mlflow: Whether to enable MLflow (set False to disable tracking)
        """
        self.enable_mlflow = enable_mlflow and MLFLOW_AVAILABLE
        self.experiment_name = experiment_name
        self.logger = logger

        if not self.enable_mlflow:
            if not MLFLOW_AVAILABLE:
                self.logger.warning(
                    "MLflow not installed. MLflow tracking disabled. "
                    "Install mlflow to enable experiment tracking."
                )
            else:
                self.logger.info("MLflow tracking disabled by configuration.")
            self._client = None
            self._experiment_id = None
            return

        # Set tracking URI from environment, argument, or default
        if tracking_uri is None:
            tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")

        mlflow.set_tracking_uri(tracking_uri)
        self.tracking_uri = tracking_uri

        # Set registry URI if provided, otherwise use tracking URI
        if registry_uri is None:
            registry_uri = os.getenv("MLFLOW_REGISTRY_URI", tracking_uri)
        self.registry_uri = registry_uri
        mlflow.set_registry_uri(registry_uri)

        # Initialize MLflow client
        try:
            self._client = MlflowClient()
            # Get or create experiment
            experiment = self._client.get_experiment_by_name(experiment_name)
            if experiment is None:
                self._experiment_id = self._client.create_experiment(experiment_name)
                self.logger.info(
                    f"Created MLflow experiment: {experiment_name} (ID: {self._experiment_id})"
                )
            else:
                self._experiment_id = experiment.experiment_id
                self.logger.info(
                    f"Using existing MLflow experiment: {experiment_name} (ID: {self._experiment_id})"
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
        """Log a strategy training run to MLflow.

        Args:
            strategy_name: Name of the strategy (used for model registry)
            parameters: Dictionary of hyperparameters and configuration
            metrics: Dictionary of performance metrics (sharpe, drawdown, etc.)
            artifacts: Optional dictionary of artifacts to log (will be saved as JSON)
            run_name: Optional name for the MLflow run

        Returns:
            Run ID if successful, None if MLflow is disabled or failed
        """
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping run logging")
            return None

        # Run MLflow operations in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            run_id = await loop.run_in_executor(
                None,
                self._log_run_sync,
                strategy_name,
                parameters,
                metrics,
                artifacts,
                run_name,
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
        """Synchronous MLflow logging (to be run in thread pool)."""
        with mlflow.start_run(
            run_name=run_name or f"{strategy_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        ) as run:
            # Log parameters
            mlflow.log_params(parameters)

            # Log metrics
            mlflow.log_metrics(metrics)

            # Set tags
            mlflow.set_tag("strategy_name", strategy_name)
            mlflow.set_tag("timestamp", datetime.utcnow().isoformat())

            # Log artifacts if provided
            if artifacts:
                # Create a temporary directory for artifacts
                import tempfile

                with tempfile.TemporaryDirectory() as tmpdir:
                    # Save each artifact as JSON file
                    for artifact_name, artifact_data in artifacts.items():
                        artifact_path = Path(tmpdir) / f"{artifact_name}.json"
                        with open(artifact_path, "w") as f:
                            json.dump(artifact_data, f, indent=2, default=str)
                    # Log the entire directory as artifacts
                    mlflow.log_artifacts(tmpdir, artifact_path="strategy_artifacts")

            # Get the run ID
            run_id = run.info.run_id

            # Log a dummy model using MLflow's pyfunc
            try:
                import mlflow.pyfunc

                class DummyModel(mlflow.pyfunc.PythonModel):
                    def predict(self, context, model_input):
                        return model_input

                # Log the model
                mlflow.pyfunc.log_model(artifact_path="model", python_model=DummyModel())
            except Exception as e:
                self.logger.warning(f"Failed to log model: {e}")
                # Fallback: log a simple artifact
                import tempfile

                with tempfile.TemporaryDirectory() as tmpdir:
                    model_path = Path(tmpdir) / "model.txt"
                    model_path.write_text(f"Dummy model for {strategy_name}")
                    mlflow.log_artifact(str(model_path), artifact_path="model")

            # Register the model in the model registry
            model_name = f"strategy_{strategy_name}"
            try:
                # Register the model
                model_uri = f"runs:/{run_id}/model"
                model_version = mlflow.register_model(model_uri, model_name)

                # Initially assign to staging stage
                self._client.transition_model_version_stage(
                    name=model_name,
                    version=model_version.version,
                    stage="Staging",
                    archive_existing_versions=False,
                )
                self.logger.info(
                    f"Registered model {model_name} version {model_version.version} in Staging stage"
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
        """Evaluate a shadow mode run and promote to production if criteria met.

        Args:
            strategy_name: Name of the strategy
            run_id: MLflow run ID to evaluate
            sharpe_threshold: Minimum Sharpe ratio for promotion
            drawdown_threshold: Maximum allowed drawdown for promotion
            hit_rate_threshold: Minimum hit rate for promotion

        Returns:
            True if promoted to production, False otherwise
        """
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
        """Synchronous evaluation and promotion (to be run in thread pool)."""
        try:
            # Get the run
            run = self._client.get_run(run_id)
            metrics = run.data.metrics

            # Extract required metrics
            sharpe = metrics.get("sharpe_ratio", 0.0)
            drawdown = metrics.get("max_drawdown", 1.0)  # Assume high if missing
            hit_rate = metrics.get("hit_rate", 0.0)

            self.logger.info(
                f"Evaluating strategy {strategy_name} (run {run_id}): "
                f"Sharpe={sharpe:.3f} (>{sharpe_threshold}), "
                f"Drawdown={drawdown:.3f} (<{drawdown_threshold}), "
                f"Hit Rate={hit_rate:.3f} (>{hit_rate_threshold})"
            )

            # Check promotion criteria
            if (
                sharpe > sharpe_threshold
                and drawdown < drawdown_threshold
                and hit_rate > hit_rate_threshold
            ):
                # Promote to production
                model_name = f"strategy_{strategy_name}"
                # Get the latest version (should be the one we just registered in staging)
                latest_versions = self._client.get_latest_versions(model_name, stages=["Staging"])
                if not latest_versions:
                    self.logger.warning(f"No staging version found for {model_name}")
                    return False

                version = latest_versions[0].version
                # Transition to production
                self._client.transition_model_version_stage(
                    name=model_name,
                    version=version,
                    stage="Production",
                    archive_existing_versions=True,  # Archive previous production version
                )
                self.logger.info(f"Promoted {model_name} version {version} to Production")
                return True
            else:
                self.logger.info(
                    f"Strategy {strategy_name} did not meet promotion criteria. "
                    f"Keeping in Staging or failing."
                )
                return False
        except Exception as e:
            self.logger.error(f"Error during evaluation and promotion: {e}")
            return False

    async def promote_if_better_than_production(
        self,
        strategy_name: str,
        shadow_run_id: str,
        sharpe_threshold: float = 1.0,
        drawdown_threshold: float = 0.1,
        hit_rate_threshold: float = 0.5,
        sharpe_improvement_threshold: float = 0.0,
        drawdown_improvement_threshold: float = 0.0,  # note: drawdown lower is better
        hit_rate_improvement_threshold: float = 0.0,
    ) -> bool:
        """Evaluate a shadow mode run and promote to production if it meets absolute thresholds and is better than the current production model.

        Args:
            strategy_name: Name of the strategy
            shadow_run_id: MLflow run ID of the shadow run to evaluate
            sharpe_threshold: Minimum Sharpe ratio for promotion
            drawdown_threshold: Maximum allowed drawdown for promotion
            hit_rate_threshold: Minimum hit rate for promotion
            sharpe_improvement_threshold: Minimum improvement in Sharpe ratio required over production (shadow - production)
            drawdown_improvement_threshold: Maximum allowed drawdown for shadow relative to production (production drawdown - shadow drawdown must be > this)
            hit_rate_improvement_threshold: Minimum improvement in hit rate required over production (shadow - production)

        Returns:
            True if promoted to production, False otherwise
        """
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping promotion")
            return False

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._promote_if_better_than_production_sync,
                strategy_name,
                shadow_run_id,
                sharpe_threshold,
                drawdown_threshold,
                hit_rate_threshold,
                sharpe_improvement_threshold,
                drawdown_improvement_threshold,
                hit_rate_improvement_threshold,
            )
            return result
        except Exception as e:
            self.logger.error(f"Failed to promote if better than production: {e}")
            return False

    def _promote_if_better_than_production_sync(
        self,
        strategy_name: str,
        shadow_run_id: str,
        sharpe_threshold: float,
        drawdown_threshold: float,
        hit_rate_threshold: float,
        sharpe_improvement_threshold: float,
        drawdown_improvement_threshold: float,
        hit_rate_improvement_threshold: float,
    ) -> bool:
        """Synchronous evaluation and promotion (to be run in thread pool)."""
        try:
            # First, evaluate the shadow run against absolute thresholds
            shadow_run = self._client.get_run(shadow_run_id)
            shadow_metrics = shadow_run.data.metrics

            # Extract required metrics from shadow run
            sharpe = shadow_metrics.get("sharpe_ratio", 0.0)
            drawdown = shadow_metrics.get("max_drawdown", 1.0)  # Assume high if missing
            hit_rate = shadow_metrics.get("hit_rate", 0.0)

            self.logger.info(
                f"Evaluating shadow strategy {strategy_name} (run {shadow_run_id}): "
                f"Sharpe={sharpe:.3f} (>{sharpe_threshold}), "
                f"Drawdown={drawdown:.3f} (<{drawdown_threshold}), "
                f"Hit Rate={hit_rate:.3f} (>{hit_rate_threshold})"
            )

            # Check absolute thresholds for shadow run
            if not (
                sharpe > sharpe_threshold
                and drawdown < drawdown_threshold
                and hit_rate > hit_rate_threshold
            ):
                self.logger.info(
                    f"Shadow strategy {strategy_name} did not meet absolute promotion criteria. "
                    f"Keeping in Staging or failing."
                )
                return False

            # If we get here, the shadow run meets absolute thresholds.
            # Now, check if there is a current production model to compare with.
            model_name = f"strategy_{strategy_name}"
            prod_versions = self._client.get_latest_versions(model_name, stages=["Production"])
            if not prod_versions:
                self.logger.info(
                    f"No production version found for {model_name}. Promoting based on absolute thresholds only."
                )
                # No production model, so we promote based on absolute thresholds
                # We need to get the version from the shadow run's model (which should be in Staging)
                staging_versions = self._client.get_latest_versions(model_name, stages=["Staging"])
                if not staging_versions:
                    self.logger.warning(f"No staging version found for {model_name} to promote")
                    return False
                version = staging_versions[0].version
                self._client.transition_model_version_stage(
                    name=model_name,
                    version=version,
                    stage="Production",
                    archive_existing_versions=False,
                )
                self.logger.info(
                    f"Promoted {model_name} version {version} from shadow run {shadow_run_id} to Production (no existing production model)"
                )
                return True

            # We have a production model, get its run ID and metrics
            prod_version = prod_versions[0]
            prod_run_id = prod_version.run_id
            prod_run = self._client.get_run(prod_run_id)
            prod_metrics = prod_run.data.metrics

            # Extract required metrics from production run
            prod_sharpe = prod_metrics.get("sharpe_ratio", 0.0)
            prod_drawdown = prod_metrics.get("max_drawdown", 1.0)
            prod_hit_rate = prod_metrics.get("hit_rate", 0.0)

            self.logger.info(
                f"Comparing with production model {model_name} version {prod_version.version} (run {prod_run_id}): "
                f"Production Sharpe={prod_sharpe:.3f}, Drawdown={prod_drawdown:.3f}, Hit Rate={prod_hit_rate:.3f}"
            )

            # Check if shadow run is better than production by the improvement thresholds
            sharpe_improvement = sharpe - prod_sharpe
            drawdown_improvement = (
                prod_drawdown - drawdown
            )  # note: we want drawdown to be lower, so improvement is positive when shadow drawdown < production drawdown
            hit_rate_improvement = hit_rate - prod_hit_rate

            if (
                sharpe_improvement > sharpe_improvement_threshold
                and drawdown_improvement > drawdown_improvement_threshold
                and hit_rate_improvement > hit_rate_improvement_threshold
            ):
                self.logger.info(
                    f"Shadow strategy {strategy_name} is better than production by thresholds: "
                    f"Sharpe improvement={sharpe_improvement:.3f} (>{sharpe_improvement_threshold}), "
                    f"Drawdown improvement={drawdown_improvement:.3f} (>{drawdown_improvement_threshold}), "
                    f"Hit rate improvement={hit_rate_improvement:.3f} (>{hit_rate_improvement_threshold})"
                )
                # Promote shadow run to production, archive existing production
                # We use the version from the shadow run's model (which should be in Staging)
                staging_versions = self._client.get_latest_versions(model_name, stages=["Staging"])
                if not staging_versions:
                    self.logger.warning(f"No staging version found for {model_name} to promote")
                    return False
                version = staging_versions[0].version
                self._client.transition_model_version_stage(
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
                self.logger.info(
                    f"Shadow strategy {strategy_name} is not sufficiently better than production. "
                    f"Sharpe improvement={sharpe_improvement:.3f} (>{sharpe_improvement_threshold}?), "
                    f"Drawdown improvement={drawdown_improvement:.3f} (>{drawdown_improvement_threshold}?), "
                    f"Hit rate improvement={hit_rate_improvement:.3f} (>{hit_rate_improvement_threshold}?)"
                )
                return False
        except Exception as e:
            self.logger.error(f"Error during evaluation and promotion: {e}")
            return False

    async def rollback_to_previous_production(self, strategy_name: str) -> bool:
        """Rollback to the previous production version.

        Args:
            strategy_name: Name of the strategy

        Returns:
            True if rollback successful, False otherwise
        """
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping rollback")
            return False

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._rollback_to_previous_production_sync,
                strategy_name,
            )
            return result
        except Exception as e:
            self.logger.error(f"Failed to rollback: {e}")
            return False

    def _rollback_to_previous_production_sync(self, strategy_name: str) -> bool:
        """Synchronous rollback (to be run in thread pool)."""
        try:
            model_name = f"strategy_{strategy_name}"
            # Get current production version
            prod_versions = self._client.get_latest_versions(model_name, stages=["Production"])
            if not prod_versions:
                self.logger.warning(f"No production version found for {model_name}")
                return False
            current_prod_version = prod_versions[0].version

            # Get previous versions that are archived (these were previous production)
            # We look for versions in the Archived stage
            archived_versions = self._client.get_latest_versions(model_name, stages=["Archived"])
            if not archived_versions:
                self.logger.warning(f"No archived version found for {model_name} to rollback to")
                return False

            # Get the most recent archived version (which was the previous production)
            # Sort by version number descending to get the latest archived
            archived_versions_sorted = sorted(
                archived_versions, key=lambda v: int(v.version), reverse=True
            )
            previous_version = archived_versions_sorted[0].version

            # Archive current production version
            self._client.transition_model_version_stage(
                name=model_name,
                version=current_prod_version,
                stage="Archived",
                archive_existing_versions=False,
            )
            # Promote the archived version back to production
            self._client.transition_model_version_stage(
                name=model_name,
                version=previous_version,
                stage="Production",
                archive_existing_versions=True,
            )
            self.logger.info(
                f"Rolled back {model_name} from version {current_prod_version} to {previous_version}"
            )
            return True
        except Exception as e:
            self.logger.error(f"Error during rollback: {e}")
            return False

    async def load_production_model(self, strategy_name: str) -> Any | None:
        """Load the latest production model for a strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            The loaded model object, or None if not found or error
        """
        if not self.enable_mlflow:
            self.logger.debug("MLflow disabled, skipping model load")
            return None

        loop = asyncio.get_event_loop()
        try:
            model = await loop.run_in_executor(
                None,
                self._load_production_model_sync,
                strategy_name,
            )
            return model
        except Exception as e:
            self.logger.error(f"Failed to load production model: {e}")
            return None

    def _load_production_model_sync(self, strategy_name: str) -> Any | None:
        """Synchronous model loading (to be run in thread pool)."""
        try:
            model_name = f"strategy_{strategy_name}"
            # Get the latest production version
            prod_versions = self._client.get_latest_versions(model_name, stages=["Production"])
            if not prod_versions:
                self.logger.warning(f"No production version found for {model_name}")
                return None

            version = prod_versions[0].version
            model_uri = f"models:/{model_name}/{version}"

            # In a real implementation, you would load your actual model here
            # For now, we'll just return the model URI as a placeholder
            # Replace this with your actual model loading logic
            self.logger.info(f"Loading model {model_name} version {version} from {model_uri}")

            # Placeholder: return model URI
            # In reality, you would do something like:
            #   model = mlflow.pyfunc.load_model(model_uri)
            #   return model
            return model_uri
        except Exception as e:
            self.logger.error(f"Error loading production model: {e}")
            return None

    def get_model_status(self, strategy_name: str) -> dict[str, Any]:
        """Get the current status of a strategy's model in the registry.

        Args:
            strategy_name: Name of the strategy

        Returns:
            Dictionary with model version and stage information
        """
        if not self.enable_mlflow:
            return {"error": "MLflow disabled"}

        try:
            model_name = f"strategy_{strategy_name}"
            # Get latest versions in each stage
            stages = ["None", "Staging", "Production", "Archived"]
            status = {}
            for stage in stages:
                versions = self._client.get_latest_versions(model_name, stages=[stage])
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
        """Check if MLflow tracking is enabled."""
        return self.enable_mlflow
