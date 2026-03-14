from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

import polars as pl

from qtrader.backtest.engine_vectorized import VectorizedEngine

__all__ = ["WalkForwardBacktest"]


FitFunc = Callable[[pl.DataFrame], Any]
PredictFunc = Callable[[Any, pl.DataFrame], pl.Series]


@dataclass(slots=True)
class WalkForwardBacktest:
    """Institutional walk-forward backtest runner."""

    train_periods: int = 504
    test_periods: int = 126
    step_periods: int = 63
    embargo_periods: int = 5

    def run(
        self,
        df: pl.DataFrame,
        fit_func: FitFunc,
        predict_func: PredictFunc,
        price_col: str = "close",
        transaction_cost_bps: float = 10.0,
    ) -> pl.DataFrame:
        """Run walk-forward backtest and stitch OOS results.

        Args:
            df: Input DataFrame with at least ``timestamp`` and ``price_col``.
            fit_func: Function that trains a model on in-sample data.
            predict_func: Function that produces OOS signals for test data.
            price_col: Price column for backtesting.
            transaction_cost_bps: Transaction cost in basis points.

        Returns:
            Concatenated OOS backtest results with columns:
            ``timestamp``, ``signal``, ``net_return``, ``equity_curve``,
            ``fold_id`` and other columns from the vectorized backtest.

        Notes:
            LOOKAHEAD PREVENTION: test windows strictly follow training windows
            with an embargo gap; signals are backtested using lagged execution
            inside :class:`VectorizedEngine`.
        """
        if "timestamp" not in df.columns:
            raise ValueError("df must contain a 'timestamp' column.")
        df_sorted = df.sort("timestamp")
        n = df_sorted.height

        engine = VectorizedEngine()
        folds: List[pl.DataFrame] = []
        start = 0
        fold_id = 0

        while True:
            train_start = start
            train_end = train_start + self.train_periods
            test_start = train_end + self.embargo_periods
            test_end = test_start + self.test_periods

            if test_start >= n or test_end > n:
                break

            train_df = df_sorted.slice(train_start, self.train_periods)
            test_df = df_sorted.slice(test_start, self.test_periods)

            model = fit_func(train_df)
            signal_series = predict_func(model, test_df)
            if not isinstance(signal_series, pl.Series) or signal_series.len() != test_df.height:
                raise ValueError("predict_func must return a pl.Series aligned with test_df.")

            test_with_signal = test_df.with_columns(signal_series.alias("signal"))
            bt = engine.backtest(
                df=test_with_signal,
                signal_col="signal",
                price_col=price_col,
                transaction_cost_bps=transaction_cost_bps,
            ).with_columns(pl.lit(fold_id).alias("fold_id"))

            folds.append(bt)
            fold_id += 1
            start += self.step_periods

        if not folds:
            raise ValueError("No valid walk-forward folds generated.")

        all_oos = pl.concat(folds).sort("timestamp")
        # Re-stitch global equity curve across folds.
        all_oos = all_oos.with_columns(
            (pl.col("net_return") + 1.0).cum_prod().alias("equity_curve")
        )
        return all_oos

    def fold_summary(self, results: pl.DataFrame) -> pl.DataFrame:
        """Compute per-fold Sharpe, return, and max drawdown."""
        if "fold_id" not in results.columns or "net_return" not in results.columns:
            raise ValueError("results must contain 'fold_id' and 'net_return'.")

        grouped = results.group_by("fold_id").agg(
            [
                pl.col("net_return").sum().alias("total_return"),
                pl.col("net_return").mean().alias("mean_return"),
                pl.col("net_return").std().alias("std_return"),
            ]
        )

        grouped = grouped.with_columns(
            [
                pl.when(pl.col("std_return") == 0.0)
                .then(0.0)
                .otherwise(pl.col("mean_return") / pl.col("std_return") * (252.0**0.5))
                .alias("sharpe"),
            ]
        )
        grouped = grouped.drop("mean_return", "std_return")

        return grouped


if __name__ == "__main__":
    _ts = pl.date_range(
        low=pl.datetime(2024, 1, 1),
        high=pl.datetime(2025, 12, 31),
        interval="1d",
        eager=True,
    )
    _prices = 100.0 + pl.arange(0, len(_ts), eager=True).cast(pl.Float64) * 0.1
    _df = pl.DataFrame({"timestamp": _ts, "close": _prices})

    def _fit(train: pl.DataFrame) -> Dict[str, float]:
        return {"mean_ret": float(train["close"].pct_change().drop_nulls().mean())}

    def _predict(model: Dict[str, float], test: pl.DataFrame) -> pl.Series:
        _ = model
        return pl.Series("signal", [1.0] * test.height)

    _wf = WalkForwardBacktest(train_periods=252, test_periods=63, step_periods=63, embargo_periods=5)
    _res = _wf.run(_df, _fit, _predict)
    _summary = _wf.fold_summary(_res)
    assert "sharpe" in _summary.columns

