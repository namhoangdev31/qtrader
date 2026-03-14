"""Unified backtest entry point: BacktestHarness wires engine, tearsheet, and analytics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

import polars as pl

from qtrader.analytics.performance import PerformanceAnalytics
from qtrader.backtest.engine_vectorized import VectorizedEngine
from qtrader.backtest.multi_asset import PortfolioBacktest
from qtrader.backtest.tearsheet import TearsheetGenerator, TearsheetMetrics
from qtrader.backtest.walk_forward_bt import WalkForwardBacktest

__all__ = [
    "BacktestHarness",
    "BacktestResult",
    "WalkForwardResult",
    "PortfolioOptimizerProtocol",
    "load_baseline_metrics",
]

_LOG = logging.getLogger("qtrader.backtest.integration")


@runtime_checkable
class PortfolioOptimizerProtocol(Protocol):
    """Protocol for portfolio optimizers (HRP, MVO, etc.)."""

    def optimize(self, returns: pl.DataFrame) -> dict[str, float]:
        """Compute weights from returns matrix. Columns = symbols."""
        ...


@dataclass(slots=True)
class BacktestResult:
    """Result of a single backtest run with metrics and optional HTML report."""

    strategy_name: str
    tearsheet: TearsheetMetrics
    backtest_df: pl.DataFrame
    html_report_path: str | None
    analytics_metrics: dict[str, float]


@dataclass(slots=True)
class WalkForwardResult:
    """Result of walk-forward backtest with stitched OOS and per-fold summary."""

    strategy_name: str
    backtest_df: pl.DataFrame
    fold_summary: pl.DataFrame
    tearsheet: TearsheetMetrics | None
    html_report_path: str | None


@dataclass(slots=True)
class BacktestHarness:
    """
    Unified entry point for all backtest modes. Wires VectorizedEngine,
    TearsheetGenerator, and PerformanceAnalytics. All other modules call this;
    do not call VectorizedEngine directly.
    """

    engine: VectorizedEngine
    tearsheet_gen: TearsheetGenerator
    portfolio_optimizer: PortfolioOptimizerProtocol | None = None
    risk_engine: object | None = None  # RealTimeRiskEngine optional; no backtest→bot import
    reports_dir: str = "reports"

    def run(
        self,
        df: pl.DataFrame,
        signal_col: str,
        strategy_name: str,
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        initial_capital: float = 100_000.0,
        benchmark: pl.Series | None = None,
        output_html: bool = True,
        price_col: str = "close",
        volume_col: str | None = None,
        impact_model: str = "square_root",
        borrowing_cost_annual_bps: float = 0.0,
    ) -> BacktestResult:
        """
        Run vectorized backtest, generate tearsheet and optional HTML report.

        Args:
            df: Full feature+signal DataFrame with timestamp, price_col, signal_col.
            signal_col: Column name for trading signal (-1/0/1).
            strategy_name: Label for report.
            transaction_cost_bps: Commission in bps.
            slippage_bps: Fixed slippage in bps when volume_col is not set.
            initial_capital: Starting equity.
            benchmark: Optional benchmark return series for comparison.
            output_html: Whether to write HTML and JSON sidecar to reports_dir.
            price_col: Price column for returns.
            volume_col: Optional volume column for market-impact slippage.
            impact_model: Impact model when volume_col is set (e.g. "square_root").
            borrowing_cost_annual_bps: Annual borrowing cost in bps when short.

        Returns:
            BacktestResult with tearsheet, backtest_df, and cross-check metrics.
        """
        backtest_df = self.engine.backtest(
            df=df,
            signal_col=signal_col,
            price_col=price_col,
            transaction_cost_bps=transaction_cost_bps,
            slippage_bps=slippage_bps,
            initial_capital=initial_capital,
            volume_col=volume_col,
            impact_model=impact_model,
            borrowing_cost_annual_bps=borrowing_cost_annual_bps,
        )
        tearsheet = self.tearsheet_gen.generate(
            backtest_df,
            strategy_name=strategy_name,
            benchmark_returns=benchmark,
        )
        equity = backtest_df["equity_curve"]
        analytics = PerformanceAnalytics.calculate_metrics(equity)

        html_path: str | None = None
        if output_html:
            Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
            monthly = self.tearsheet_gen.monthly_returns_table(
                backtest_df["equity_curve"],
                backtest_df["timestamp"],
            )
            out_path = str(Path(self.reports_dir) / f"tearsheet_{strategy_name}.html")
            html_path = self.tearsheet_gen.to_html(
                tearsheet,
                monthly,
                backtest_df,
                out_path,
                write_json_sidecar=True,
                strategy_name=strategy_name,
            )

        return BacktestResult(
            strategy_name=strategy_name,
            tearsheet=tearsheet,
            backtest_df=backtest_df,
            html_report_path=html_path,
            analytics_metrics=analytics,
        )

    def run_walk_forward(
        self,
        df: pl.DataFrame,
        fit_func: Callable[[pl.DataFrame], object],
        predict_func: Callable[[object, pl.DataFrame], pl.Series],
        strategy_name: str,
        train_periods: int = 504,
        test_periods: int = 126,
        step_periods: int = 63,
        embargo_periods: int = 5,
        transaction_cost_bps: float = 10.0,
        output_html: bool = True,
        price_col: str = "close",
    ) -> WalkForwardResult:
        """
        Run walk-forward backtest and generate per-fold or aggregate tearsheet.

        Args:
            df: DataFrame with timestamp, price_col, and feature columns for model.
            fit_func: Trains on train_df, returns model object.
            predict_func: (model, test_df) -> signal Series aligned with test_df.
            strategy_name: Label for report.
            train_periods: Training window length.
            test_periods: Test window length.
            step_periods: Step between folds.
            embargo_periods: Gap between train and test.
            transaction_cost_bps: Cost in bps.
            output_html: Whether to write HTML report.
            price_col: Price column name.

        Returns:
            WalkForwardResult with backtest_df, fold_summary, and optional tearsheet.
        """
        wf = WalkForwardBacktest(
            train_periods=train_periods,
            test_periods=test_periods,
            step_periods=step_periods,
            embargo_periods=embargo_periods,
        )
        backtest_df = wf.run(
            df=df,
            fit_func=fit_func,
            predict_func=predict_func,
            price_col=price_col,
            transaction_cost_bps=transaction_cost_bps,
        )
        fold_summary = wf.fold_summary(backtest_df)
        tearsheet = self.tearsheet_gen.generate(backtest_df, strategy_name=strategy_name)
        html_path: str | None = None
        if output_html:
            Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
            monthly = self.tearsheet_gen.monthly_returns_table(
                backtest_df["equity_curve"],
                backtest_df["timestamp"],
            )
            out_path = str(Path(self.reports_dir) / f"wf_tearsheet_{strategy_name}.html")
            html_path = self.tearsheet_gen.to_html(
                tearsheet,
                monthly,
                backtest_df,
                out_path,
                write_json_sidecar=True,
                strategy_name=strategy_name,
            )
        return WalkForwardResult(
            strategy_name=strategy_name,
            backtest_df=backtest_df,
            fold_summary=fold_summary,
            tearsheet=tearsheet,
            html_report_path=html_path,
        )

    def run_portfolio(
        self,
        prices: pl.DataFrame,
        signals: pl.DataFrame,
        strategy_name: str,
        optimizer: str = "hrp",
        transaction_cost_bps: float = 10.0,
        initial_capital: float = 1_000_000.0,
        output_html: bool = True,
        **kwargs: object,
    ) -> BacktestResult:
        """
        Run portfolio backtest with selected optimizer (hrp | equal).

        Args:
            prices: Wide DataFrame with timestamp and one column per symbol.
            signals: Wide DataFrame with same structure as prices.
            strategy_name: Label for report.
            optimizer: "hrp" or "equal".
            transaction_cost_bps: Cost in bps.
            initial_capital: Starting capital.
            output_html: Whether to write HTML report.
            **kwargs: Passed to PortfolioBacktest.

        Returns:
            BacktestResult with tearsheet and backtest_df.
        """
        from qtrader.portfolio.hrp import HRPOptimizer

        symbol_cols = [c for c in prices.columns if c != "timestamp"]
        allowed = {"rebalance_freq", "allow_leverage", "max_position_pct"}
        pb_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        pb = PortfolioBacktest(
            transaction_cost_bps=transaction_cost_bps,
            initial_capital=initial_capital,
            **pb_kwargs,
        )
        weights_df: pl.DataFrame | None = None
        if optimizer == "hrp":
            opt = self.portfolio_optimizer or HRPOptimizer()
            returns = prices.select(
                [pl.col(c).pct_change().alias(c) for c in symbol_cols]
            ).drop_nulls()
            if returns.height > 0:
                weights_dict = opt.optimize(returns)
                weights_df = prices.select("timestamp").with_columns(
                    [pl.lit(weights_dict.get(s, 0.0)).alias(s) for s in symbol_cols]
                )
        results = pb.run(prices, signals, weights=weights_df)
        tearsheet = self.tearsheet_gen.generate(results, strategy_name=strategy_name)
        equity = results["equity_curve"]
        analytics = PerformanceAnalytics.calculate_metrics(equity)
        html_path = None
        if output_html:
            Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
            monthly = self.tearsheet_gen.monthly_returns_table(
                results["equity_curve"],
                results["timestamp"],
            )
            out_path = str(Path(self.reports_dir) / f"portfolio_tearsheet_{strategy_name}.html")
            html_path = self.tearsheet_gen.to_html(
                tearsheet,
                monthly,
                results,
                out_path,
                write_json_sidecar=True,
                strategy_name=strategy_name,
            )
        return BacktestResult(
            strategy_name=strategy_name,
            tearsheet=tearsheet,
            backtest_df=results,
            html_report_path=html_path,
            analytics_metrics=analytics,
        )


def load_baseline_metrics(path: str | None = None) -> TearsheetMetrics | None:
    """
    Load baseline TearsheetMetrics from JSON sidecar for LiveMonitor.

    Args:
        path: Path to JSON file. Defaults to reports/latest_baseline.json.

    Returns:
        TearsheetMetrics if file exists, else None.
    """
    p = Path(path or "reports/latest_baseline.json").expanduser().absolute()
    if not p.exists():
        return None
    return TearsheetMetrics.from_json(p)


if __name__ == "__main__":
    # Pytest-style examples (run with python -m qtrader.backtest.integration)
    import polars as pl  # noqa: F401

    _ts = pl.datetime_range(
        start=pl.datetime(2024, 1, 1),
        end=pl.datetime(2024, 6, 1),
        interval="1d",
        eager=True,
    )
    _n = len(_ts)
    _df = pl.DataFrame({
        "timestamp": _ts,
        "close": 100.0 + pl.arange(0, _n, eager=True).cast(pl.Float64) * 0.1,
        "signal": (pl.arange(0, _n, eager=True) % 3 - 1).cast(pl.Float64),
    })
    _harness = BacktestHarness(
        engine=VectorizedEngine(),
        tearsheet_gen=TearsheetGenerator(),
    )
    _res = _harness.run(_df, signal_col="signal", strategy_name="demo", output_html=False)
    assert _res.tearsheet.sharpe_ratio is not None
    assert "equity_curve" in _res.backtest_df.columns
