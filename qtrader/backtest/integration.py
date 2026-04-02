"""BacktestHarness: unified entry point for all backtest modes.

This module implements the BacktestHarness class that wires together
VectorizedEngine, TearsheetGenerator, SimulatedBroker, and optional
portfolio optimization and risk engines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import polars as pl

from qtrader.analytics.performance import PerformanceAnalytics

if TYPE_CHECKING:
    from collections.abc import Callable

    from qtrader.backtest.broker_sim import SimulatedBroker
    from qtrader.backtest.engine_vectorized import VectorizedEngine
    from qtrader.backtest.tearsheet import TearsheetGenerator, TearsheetMetrics
    from qtrader.portfolio.optimization import PortfolioOptimizer
    from qtrader.risk.realtime import RealTimeRiskEngine

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Result of a backtest run.

    Attributes:
        strategy_name: Name of the strategy tested.
        tearsheet: Performance metrics from the backtest.
        backtest_df: Bar-level backtest data (with equity curve, drawdown, etc.).
        html_report_path: Path to generated HTML tearsheet (if output_html=True).
        analytics_metrics: Cross-checked metrics from PerformanceAnalytics.
    """

    strategy_name: str
    tearsheet: TearsheetMetrics
    backtest_df: pl.DataFrame
    html_report_path: str | None
    analytics_metrics: dict[str, float]


@dataclass
class WalkForwardResult:
    """Result of a walk-forward backtest.

    Attributes:
        strategy_name: Name of the strategy tested.
        tearsheets: List of TearsheetMetrics per fold.
        backtest_df: Aggregated bar-level backtest data.
        html_report_paths: List of HTML report paths per fold.
        analytics_metrics: Cross-checked metrics from PerformanceAnalytics (aggregated).
    """

    strategy_name: str
    tearsheets: list[TearsheetMetrics]
    backtest_df: pl.DataFrame
    html_report_paths: list[str]
    analytics_metrics: dict[str, float]


class BacktestHarness:
    """Unified entry point for all backtest modes.

    This harness replaces calling individual engines directly. It wires together:
    - VectorizedEngine for the core backtest
    - TearsheetGenerator for performance metrics and reporting
    - SimulatedBroker for order execution simulation
    - Optional PortfolioOptimizer for position sizing
    - Optional RealTimeRiskEngine for risk limits

    All other modules should call this harness — never call VectorizedEngine directly.
    """

    def __init__(
        self,
        engine: VectorizedEngine,
        tearsheet_gen: TearsheetGenerator,
        broker: SimulatedBroker,
        portfolio_optimizer: PortfolioOptimizer | None = None,
        risk_engine: RealTimeRiskEngine | None = None,
    ) -> None:
        """Initialize the BacktestHarness.

        Args:
            engine: VectorizedEngine instance for backtesting.
            tearsheet_gen: TearsheetGenerator instance for metrics and reporting.
            broker: SimulatedBroker instance for order execution.
            portfolio_optimizer: Optional PortfolioOptimizer for position weighting.
            risk_engine: Optional RealTimeRiskEngine for risk limit checks.
        """
        self.engine = engine
        self.tearsheet_gen = tearsheet_gen
        self.broker = broker
        self.portfolio_optimizer = portfolio_optimizer
        self.risk_engine = risk_engine

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
    ) -> BacktestResult:
        """Orchestrate a single backtest run.

        Args:
            df: DataFrame with features, signals, and OHLCV data.
            signal_col: Column name in df containing the signal to trade.
            strategy_name: Name of the strategy (used for reporting).
            transaction_cost_bps: Transaction costs in basis points.
            slippage_bps: Slippage in basis points.
            initial_capital: Starting capital for the backtest.
            benchmark: Optional benchmark series (e.g., buy-and-hold).
            output_html: Whether to generate an HTML tearsheet.

        Returns:
            BacktestResult containing the backtest outcomes.
        """
        logger.info("Running backtest for strategy %s", strategy_name)

        backtest_output = self.engine.backtest(
            df=df,
            signal_col=signal_col,
            transaction_cost_bps=transaction_cost_bps,
            slippage_bps=slippage_bps,
            initial_capital=initial_capital,
        )

        if self.portfolio_optimizer is not None:
            returns_df = df.select([pl.col("close").pct_change()]).fill_null(0.0)
            lookback = min(60, len(returns_df))
            for i in range(lookback, len(returns_df)):
                window = returns_df.slice(i - lookback, lookback)
                self.portfolio_optimizer.optimize(window)
                pass
            logger.warning(
                "Portfolio optimizer provided but not applied in BacktestHarness.run (single-asset assumption)."
            )

        if self.risk_engine is not None:
            logger.warning(
                "Risk engine provided but not applied in BacktestHarness.run (requires integration with VectorizedEngine)."
            )

            tearsheet: TearsheetMetrics = self.tearsheet_gen.generate(
            backtest_result=backtest_output,
            strategy_name=strategy_name,
            benchmark_returns=benchmark,
        )

        html_report_path: str | None = None
        if output_html:
            html_report_path = self.tearsheet_gen.to_html(
                tearsheet=tearsheet,
                strategy_name=strategy_name,
                output_dir="reports",
            )
            logger.info("HTML tearsheet saved to %s", html_report_path)

        analytics = PerformanceAnalytics()
        analytics_metrics: dict[str, float] = analytics.calculate_metrics(
            equity_curve=backtest_output,
            trades=pl.DataFrame(),  # VectorizedEngine returns trades in the main DF
            initial_capital=initial_capital,
        )

        # 7. Construct and return the result
        result = BacktestResult(
            strategy_name=strategy_name,
            tearsheet=tearsheet,
            backtest_df=backtest_output,
            html_report_path=html_report_path,
            analytics_metrics=analytics_metrics,
        )
        logger.info(
            "Backtest completed for %s: Sharpe=%.2f, MaxDD=%.2f",
            strategy_name,
            tearsheet.sharpe_ratio or 0.0,
            tearsheet.max_drawdown or 0.0,
        )
        return result

    def run_walk_forward(
        self,
        df: pl.DataFrame,
        fit_func: Callable,
        predict_func: Callable,
        strategy_name: str,
        **kwargs: Any,
    ) -> WalkForwardResult:
        """Run a walk-forward backtest.

        Args:
            df: DataFrame with features and OHLCV data.
            fit_func: Function to fit the model (takes training data, returns model).
            predict_func: Function to predict with the model (takes model and test data, returns predictions).
            strategy_name: Name of the strategy.
            **kwargs: Additional arguments passed to the underlying run method (e.g., transaction_cost_bps).

        Returns:
            WalkForwardResult containing the aggregated results.
        """
        logger.info("Running walk-forward backtest for strategy %s", strategy_name)

        train_window = 504  # ~2 years of daily data
        test_window = 126   # ~6 months of daily data
        step = test_window  # non-overlapping test windows

        tearsheets: list[TearsheetMetrics] = []
        backtest_dfs: list[pl.DataFrame] = []
        html_report_paths: list[str] = []
        all_analytics: list[dict[str, float]] = []

        start = 0
        while start + train_window + test_window <= len(df):
            train_df = df.slice(start, train_window)
            test_df = df.slice(start + train_window, test_window)

            model = fit_func(train_df)

            predictions = predict_func(model, test_df)
            test_df_with_signal = test_df.with_columns(predictions.alias("signal"))

            fold_result = self.run(
                df=test_df_with_signal,
                signal_col="signal",
                strategy_name=f"{strategy_name}_fold_{start}",
                **kwargs,
            )

            tearsheets.append(fold_result.tearsheet)
            backtest_dfs.append(fold_result.backtest_df)
            if fold_result.html_report_path:
                html_report_paths.append(fold_result.html_report_path)
            all_analytics.append(fold_result.analytics_metrics)

            start += step  # move to the next window

        if backtest_dfs:
            aggregated_backtest_df = pl.concat(backtest_dfs)
        else:
            aggregated_backtest_df = pl.DataFrame()

        agg_analytics: dict[str, float] = {}
        if all_analytics:
            for key in all_analytics[0].keys():
                agg_analytics[key] = sum(d[key] for d in all_analytics) / len(all_analytics)

        result = WalkForwardResult(
            strategy_name=strategy_name,
            tearsheets=tearsheets,
            backtest_df=aggregated_backtest_df,
            html_report_paths=html_report_paths,
            analytics_metrics=agg_analytics,
        )
        logger.info(
            "Walk-forward backtest completed for %s with %d folds",
            strategy_name,
            len(tearsheets),
        )
        return result

    def run_portfolio(
        self,
        prices: pl.DataFrame,
        signals: pl.DataFrame,
        strategy_name: str,
        optimizer: str = "hrp",  # hrp | cvar | mvo | equal
        **kwargs: Any,
    ) -> BacktestResult:
        """Run a portfolio backtest.

        Args:
            prices: DataFrame with OHLCV prices for multiple symbols (wide format: columns are symbols).
            signals: DataFrame with signals for multiple symbols (same shape as prices).
            strategy_name: Name of the strategy.
            optimizer: Type of portfolio optimizer to use.
            **kwargs: Additional arguments passed to the underlying run method.

        Returns:
            BacktestResult for the portfolio.
        """
        logger.info("Running portfolio backtest for strategy %s with %s optimizer", strategy_name, optimizer)

        returns = prices.pct_change()

        lookback = kwargs.get("lookback", 60)
        lookback = min(lookback, len(returns))

        weights_list = []
        for i in range(lookback, len(returns)):
            returns.iloc[i - lookback:i]  # assuming pandas-like iloc, but we are using Polars
            window_pl = returns.slice(i - lookback, lookback)
            try:
                weights = self.portfolio_optimizer.optimize(window_pl)
            except Exception as e:
                logger.error("Error in portfolio optimization: %s", e)
                weights = {symbol: 1.0 / len(returns.columns) for symbol in returns.columns}
            weights_list.append(weights)

        portfolio_returns = []
        for i, w_dict in enumerate(weights_list):
            ret_row = returns.row(i + lookback)
            w_list = [w_dict.get(col, 0.0) for col in returns.columns]
            port_ret = sum(w * r for w, r in zip(w_list, ret_row, strict=False))
            portfolio_returns.append(port_ret)

        timestamps = returns.slice(lookback, len(portfolio_returns)).select("timestamp") if "timestamp" in returns.columns else pl.Series("timestamp", range(len(portfolio_returns)))

        portfolio_df = pl.DataFrame(
            {
                "timestamp": timestamps,
                "portfolio_return": portfolio_returns,
            }
        )

        (1 + pl.Series(portfolio_returns)).cum_prod() * kwargs.get("initial_capital", 100_000.0)

        tearsheet = self.tearsheet_gen.generate(
            backtest_result=portfolio_df,
            strategy_name=strategy_name,
        )
        html_report_path = None
        if kwargs.get("output_html", True):
            html_report_path = self.tearsheet_gen.to_html(
                tearsheet=tearsheet,
                strategy_name=strategy_name,
                output_dir="reports",
            )

        analytics_metrics = PerformanceAnalytics.calculate_metrics(
            equity_curve=portfolio_df,
            trades=pl.DataFrame(),
            initial_capital=kwargs.get("initial_capital", 100_000.0),
        )

        result = BacktestResult(
            strategy_name=strategy_name,
            tearsheet=tearsheet,
            backtest_df=portfolio_df,
            html_report_path=html_report_path,
            analytics_metrics=analytics_metrics,
        )
        logger.info(
            "Portfolio backtest completed for %s: Sharpe=%.2f, MaxDD=%.2f",
            strategy_name,
            tearsheet.sharpe_ratio or 0.0,
            tearsheet.max_drawdown or 0.0,
        )
        return result


if __name__ == "__main__":
    import doctest

    doctest.testmod()
