from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict

import numpy as np
import polars as pl
import ray
from ray import tune

from qtrader.core.config import Config
from qtrader.ml.evaluation import ModelEvaluator
from qtrader.ml.walk_forward import WalkForwardPipeline

__all__ = ["RayCompute", "RayHyperparamTuner"]


class RayCompute:
    """Helper for distributed task execution using Ray (local or cluster)."""

    def __init__(self) -> None:
        if not ray.is_initialized():
            ray.init(
                address=Config.RAY_ADDRESS,
                _memory=Config.RAY_MEMORY if Config.RAY_ADDRESS == "auto" else None,
                num_cpus=Config.RAY_CPUS if Config.RAY_ADDRESS == "auto" else None,
                ignore_reinit_error=True,
            )

    @staticmethod
    def run_parallel(func: Callable[..., Any], tasks_args: list[tuple[Any, ...]]) -> list[Any]:
        """Run a function in parallel over a list of arguments."""
        remote_func = ray.remote(func)
        futures = [remote_func.remote(*args) for args in tasks_args]
        return ray.get(futures)

    def shutdown(self) -> None:
        """Shutdown the underlying Ray runtime."""
        if ray.is_initialized():
            ray.shutdown()


class RayHyperparamTuner:
    """Distributed hyperparameter optimization using Ray Tune.

    Each trial:
      * Instantiates ``model_cls`` with sampled hyperparameters.
      * Runs a walk-forward backtest using ``WalkForwardPipeline``.
      * Reports Sharpe (or another metric) to Ray Tune.

    Args:
        n_trials: Number of Ray Tune trials.
        metric: Optimization metric (default: ``\"sharpe\"``).
        mode: ``\"max\"`` or ``\"min\"`` for the metric.
        ray_address: Ray cluster address (``\"auto\"`` for local).
    """

    def __init__(
        self,
        n_trials: int = 50,
        metric: str = "sharpe",
        mode: str = "max",
        ray_address: str = "auto",
    ) -> None:
        self.n_trials = n_trials
        self.metric = metric
        self.mode = mode
        self.ray_address = ray_address
        self._evaluator = ModelEvaluator()

    def tune(
        self,
        model_cls: type,
        param_space: Dict[str, Any],
        df: pl.DataFrame,
        wf_pipeline: WalkForwardPipeline,
        target_col: str = "forward_return",
        feature_cols: list[str] | None = None,
    ) -> Dict[str, Any]:
        """Run Ray Tune to optimize hyperparameters.

        Args:
            model_cls: Model class with ``fit(X, y)`` and ``predict(X)`` methods.
            param_space: Ray Tune parameter space dictionary.
            df: Full dataset as Polars DataFrame.
            wf_pipeline: Walk-forward pipeline for backtesting.
            target_col: Column containing forward returns.
            feature_cols: Optional list of feature columns.

        Returns:
            Best hyperparameter configuration found.
        """
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in DataFrame.")

        if feature_cols is None:
            feature_cols = [c for c in df.columns if c not in {target_col, "timestamp"}]

        dataset_serialized = df.to_pandas()  # external boundary; small-ish by design

        def trainable(config: Dict[str, Any]) -> None:
            import pandas as pd  # local import for Ray workers

            pdf: pd.DataFrame = dataset_serialized.copy()
            local_df = pl.from_pandas(pdf)
            splits = wf_pipeline.get_splits(local_df)
            if not splits:
                tune.report(**{self.metric: 0.0})
                return

            scores: list[float] = []
            for train_df, test_df in splits:
                x_train = train_df.select(feature_cols).to_numpy()
                y_train = train_df[target_col].to_numpy()

                model = model_cls(**config)
                if not hasattr(model, "fit") or not hasattr(model, "predict"):
                    raise ValueError("model_cls must implement fit() and predict().")
                model.fit(x_train, y_train)

                x_test = test_df.select(feature_cols).to_numpy()
                y_test = test_df[target_col]
                preds = np.asarray(model.predict(x_test), dtype=float)
                pred_s = pl.Series("predicted", preds)
                score = self._evaluator.compute_ic(pred_s, y_test)
                scores.append(score)

            metric_val = float(np.mean(scores)) if scores else 0.0
            tune.report(**{self.metric: metric_val})

        if not ray.is_initialized():
            ray.init(address=self.ray_address, ignore_reinit_error=True)

        tuner = tune.Tuner(
            trainable,
            tune_config=tune.TuneConfig(
                metric=self.metric,
                mode=self.mode,
                num_samples=self.n_trials,
            ),
            param_space=param_space,
        )
        result = tuner.fit()
        best_config = result.get_best_result(metric=self.metric, mode=self.mode).config
        return dict(best_config)


if __name__ == "__main__":
    import polars as pl  # type: ignore[reimported]
    from sklearn.linear_model import LinearRegression

    _df = pl.DataFrame(
        {
            "x": pl.arange(0, 50, eager=True),
            "forward_return": pl.arange(0, 50, eager=True).cast(pl.Float64),
        }
    )
    _wf = WalkForwardPipeline(train_size=30, test_size=5, embargo=0)

    _tuner = RayHyperparamTuner(n_trials=1)
    _space = {"fit_intercept": tune.choice([True, False])}
    _best = _tuner.tune(
        model_cls=LinearRegression,
        param_space=_space,
        df=_df,
        wf_pipeline=_wf,
        target_col="forward_return",
        feature_cols=["x"],
    )
    assert isinstance(_best, dict)

