from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
from scipy.stats import spearmanr

from qtrader.ml.walk_forward import WalkForwardPipeline

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["ModelEvaluator", "NestedCrossValidation"]


class ModelEvaluator:
    """Quant-standard model evaluation utilities (IC, stability, backtest)."""

    def compute_ic(self, predicted: pl.Series, realized: pl.Series) -> float:
        """Compute Spearman rank Information Coefficient.

        Args:
            predicted: Model predictions (signal scores).
            realized: Realized forward returns.

        Returns:
            Spearman rank correlation coefficient.
        """
        if len(predicted) != len(realized):
            raise ValueError("predicted and realized must have the same length.")
        if len(predicted) == 0:
            return 0.0
        pred_np = predicted.to_numpy()
        real_np = realized.to_numpy()
        ic, _ = spearmanr(pred_np, real_np)
        if ic is None or np.isnan(ic):
            return 0.0
        return float(ic)

    def rolling_ic(
        self,
        predictions_df: pl.DataFrame,
        window: int = 30,
    ) -> pl.Series:
        """Compute rolling IC over time.

        Args:
            predictions_df: DataFrame with columns ``timestamp``, ``predicted``,
                and ``realized``.
            window: Rolling window size.

        Returns:
            Polars Series of rolling IC values aligned with the input rows.
        """
        required = {"predicted", "realized"}
        missing = required - set(predictions_df.columns)
        if missing:
            raise ValueError(f"predictions_df is missing columns: {missing}")
        if window <= 1:
            raise ValueError("window must be greater than 1.")

        def _ic_window(pred: np.ndarray, real: np.ndarray) -> float:
            ic, _ = spearmanr(pred, real)
            if ic is None or np.isnan(ic):
                return 0.0
            return float(ic)

        pred_np = predictions_df["predicted"].to_numpy()
        real_np = predictions_df["realized"].to_numpy()
        n = pred_np.shape[0]
        out = np.zeros(n, dtype=float)
        for i in range(n):
            if i + 1 < window:
                out[i] = 0.0
                continue
            sl = slice(i + 1 - window, i + 1)
            out[i] = _ic_window(pred_np[sl], real_np[sl])
        return pl.Series("rolling_ic", out)

    def icir(self, ic_series: pl.Series) -> float:
        """Compute IC Information Ratio (ICIR).

        Args:
            ic_series: Series of IC values.

        Returns:
            ICIR = mean(IC) / std(IC) or 0 if std is zero.
        """
        if ic_series.len() == 0:
            return 0.0
        vals = ic_series.to_numpy()
        mean = float(np.nanmean(vals))
        std = float(np.nanstd(vals))
        if std == 0.0:
            return 0.0
        return mean / std

    def feature_importance_report(
        self,
        model: Any,
        feature_names: list[str],
    ) -> pl.DataFrame:
        """Extract feature importance from tree/linear models.

        Supports ``feature_importances_`` (tree ensembles) and ``coef_`` for
        linear models. Unknown models will return an empty table.

        Args:
            model: Fitted sklearn/xgboost/lightgbm model.
            feature_names: List of feature names in order.

        Returns:
            Polars DataFrame with columns: ``feature``, ``importance``, ``rank``.
        """
        importances: np.ndarray | None = None
        if hasattr(model, "feature_importances_"):
            importances = np.asarray(model.feature_importances_, dtype=float)
        elif hasattr(model, "coef_"):
            coef = np.asarray(model.coef_, dtype=float)
            importances = np.abs(coef).ravel()

        if importances is None:
            return pl.DataFrame(
                {
                    "feature": feature_names,
                    "importance": [0.0] * len(feature_names),
                    "rank": [0] * len(feature_names),
                }
            )

        if importances.shape[0] != len(feature_names):
            raise ValueError("Length of importances does not match feature_names.")

        df = pl.DataFrame(
            {
                "feature": feature_names,
                "importance": importances.tolist(),
            }
        ).sort("importance", descending=True)
        df = df.with_columns(pl.arange(1, df.height + 1).alias("rank"))
        return df

    def backtest_predictions(
        self,
        df: pl.DataFrame,
        transaction_cost_bps: float = 10.0,
    ) -> dict[str, float]:
        """Run a quick vectorized backtest over predictions.

        Args:
            df: DataFrame with at least ``timestamp``, ``close``, and
                ``predicted_signal`` columns. ``predicted_signal`` is interpreted
                as a trading signal in ``{-1, 0, 1}``.
            transaction_cost_bps: Transaction cost in basis points.

        Returns:
            Dictionary with keys: ``sharpe``, ``total_return``, ``max_dd``, ``ic``.
        """
        required = {"close", "predicted_signal"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"df is missing required columns: {missing}")

        signal_col = "predicted_signal"
        df_local = df.with_columns(
            [
                pl.col(signal_col).shift(1).alias("_exec_signal"),
                pl.col("close").pct_change().alias("_asset_return"),
            ]
        )
        df_local = df_local.with_columns(
            [
                (pl.col("_exec_signal") * pl.col("_asset_return")).alias("strategy_return"),
                pl.col("_exec_signal").diff().abs().fill_null(0).alias("_turnover"),
            ]
        )
        cost = transaction_cost_bps / 10_000.0
        df_local = df_local.with_columns(
            [(pl.col("strategy_return") - pl.col("_turnover") * cost).alias("net_return")]
        )
        df_local = df_local.with_columns(
            [(pl.col("net_return") + 1.0).cum_prod().alias("equity_curve")]
        )

        net_ret = df_local["net_return"].to_numpy()
        total_return = float(df_local["equity_curve"].tail(1).item() - 1.0)
        if net_ret.size == 0:
            return {"sharpe": 0.0, "total_return": 0.0, "max_dd": 0.0, "ic": 0.0}

        mean = float(np.nanmean(net_ret))
        std = float(np.nanstd(net_ret))
        sharpe = 0.0 if std == 0.0 else mean / std * np.sqrt(252.0)

        equity = df_local["equity_curve"].to_numpy()
        running_max = np.maximum.accumulate(equity)
        dd = (equity - running_max) / running_max
        max_dd = float(dd.min()) if dd.size > 0 else 0.0

        # IC vs next-period returns
        realized = df_local["_asset_return"].shift(-1).drop_nulls()
        aligned_pred = df_local[signal_col].shift(0).head(len(realized))
        ic = self.compute_ic(aligned_pred, realized) if len(realized) > 0 else 0.0

        return {"sharpe": sharpe, "total_return": total_return, "max_dd": max_dd, "ic": ic}


class NestedCrossValidation:
    """Nested walk-forward cross-validation using IC as the score."""

    def __init__(
        self,
        outer_pipeline: WalkForwardPipeline,
        inner_pipeline: WalkForwardPipeline,
    ) -> None:
        """Initialize nested cross-validation.

        Args:
            outer_pipeline: Walk-forward splitter for the outer loop.
            inner_pipeline: Walk-forward splitter for the inner loop.
        """
        self.outer = outer_pipeline
        self.inner = inner_pipeline
        self._evaluator = ModelEvaluator()

    def evaluate(
        self,
        df: pl.DataFrame,
        train_func: Callable[[pl.DataFrame, dict[str, Any]], Any],
        param_grid: list[dict[str, Any]],
        target_col: str = "forward_return",
        feature_cols: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run nested cross-validation with IC-based scoring.

        Args:
            df: Input DataFrame.
            train_func: Callable that trains a model on a training split and
                returns a fitted model.
            param_grid: List of hyperparameter dictionaries to try.
            target_col: Name of the realized-return column.
            feature_cols: Optional list of feature columns. If None, all
                non-target columns (excluding timestamp-like) are used.

        Returns:
            List of dictionaries with fold index, best params, and test IC.
        """
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in DataFrame.")

        results: list[dict[str, Any]] = []
        outer_splits = self.outer.get_splits(df)

        for i, (outer_train, outer_test) in enumerate(outer_splits):
            best_params: dict[str, Any] | None = None
            best_inner_score = float("-inf")

            inner_splits = self.inner.get_splits(outer_train)
            for params in param_grid:
                scores: list[float] = []
                for inner_train, inner_val in inner_splits:
                    model = train_func(inner_train, params)
                    score = self._score(model, inner_val, target_col, feature_cols)
                    scores.append(score)

                if not scores:
                    continue
                avg_score = float(np.mean(scores))
                if avg_score > best_inner_score:
                    best_inner_score = avg_score
                    best_params = params

            if best_params is None:
                continue

            final_model = train_func(outer_train, best_params)
            test_score = self._score(final_model, outer_test, target_col, feature_cols)
            results.append(
                {
                    "fold": i,
                    "best_params": best_params,
                    "test_ic": test_score,
                }
            )

        return results

    def _score(
        self,
        model: Any,
        df: pl.DataFrame,
        target_col: str,
        feature_cols: list[str] | None,
    ) -> float:
        """Compute IC between model predictions and forward returns."""
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in DataFrame.")

        if feature_cols is None:
            feature_cols = [c for c in df.columns if c not in {target_col, "timestamp"}]
        x = df.select(feature_cols).to_numpy()
        y = df[target_col]

        if not hasattr(model, "predict"):
            raise ValueError("Model must implement a predict() method.")
        pred_np = np.asarray(model.predict(x), dtype=float)
        predicted = pl.Series("predicted", pred_np)
        return self._evaluator.compute_ic(predicted, y)


if __name__ == "__main__":
    import asyncio

    import polars as pl
    from sklearn.linear_model import LinearRegression

    from qtrader.core.event_bus import EventBus
    from qtrader.core.orchestrator import TradingOrchestrator

    # 1. Mandatory Sovereign Initialization
    # Ensures deterministic seeds and audit logging for the evaluation script
    orch = TradingOrchestrator(
        event_bus=EventBus(),
        market_data_adapter=object(),
        alpha_modules=[],
        feature_validator=None,
        strategies=[],
        ensemble_strategy=None,
        portfolio_allocator=None,
        runtime_risk_engine=None,
        oms_adapter=None,
    )
    orch.initialize()
    orch.validate()

    # 2. Evaluation Logic
    _df = pl.DataFrame(
        {
            "x": [0.0, 1.0, 2.0, 3.0, 4.0],
            "forward_return": [0.1, 0.2, -0.1, 0.05, 0.0],
        }
    )
    _outer = WalkForwardPipeline(train_size=3, test_size=1, embargo=0)
    _inner = WalkForwardPipeline(train_size=3, test_size=1, embargo=0)

    def _train(train_df: pl.DataFrame, params: dict[str, Any]) -> Any:
        x_train = train_df.select(["x"]).to_numpy()
        y_train = train_df["forward_return"].to_numpy()
        model = LinearRegression(**params)
        model.fit(x_train, y_train)
        return model

    _nc = NestedCrossValidation(_outer, _inner)
    _res = _nc.evaluate(
        _df,
        target_col="forward_return",
        train_func=_train,
        param_grid=[{}],
        feature_cols=["x"],
    )
    if not isinstance(_res, list):
        raise TypeError("Evaluation result must be a list")
    print(f"Evaluation Complete | Result Count: {len(_res)}")

    # 3. Graceful Clean Halt
    asyncio.run(orch.halt_core("Evaluation_Script_Finished"))
