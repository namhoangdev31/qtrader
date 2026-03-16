"""Session bridge: AnalystSession ↔ ResearchPipeline and BacktestHarness."""

from __future__ import annotations

import logging
import polars as pl

from qtrader.backtest.integration import BacktestHarness
from qtrader.output.bot.performance import PerformanceTracker
from qtrader.pipeline.deployment import DeploymentBridge
from qtrader.pipeline.research import ResearchPipeline, ResearchResult

__all__ = ["SessionBridge"]

_LOG = logging.getLogger("qtrader.pipeline.session_bridge")


class SessionBridge:
    """
    Connects AnalystSession (notebook/manual) to the automated pipeline.
    Use in Jupyter to trigger pipeline runs and inspect results.
    """

    def __init__(
        self,
        pipeline: ResearchPipeline,
        harness: BacktestHarness,
        deployment: DeploymentBridge | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.harness = harness
        self.deployment = deployment or DeploymentBridge()

    def quick_backtest(
        self,
        symbol: str,
        strategy: str = "momentum",
        lookback_days: int = 365,
        show_html: bool = True,
    ) -> ResearchResult:
        """
        One-liner full pipeline for one symbol. Optionally opens HTML tearsheet.

        Args:
            symbol: Single symbol (e.g. "BTC/USDT").
            strategy: Strategy name.
            lookback_days: Days of history to load.
            show_html: If True, open the generated HTML report in browser.

        Returns:
            ResearchResult from pipeline.run().
        """
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        result = self.pipeline.run(
            symbols=[symbol],
            timeframe="1d",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            strategy_name=strategy,
        )
        html_path = getattr(result, "html_report_path", None)
        if show_html and html_path:
            try:
                import webbrowser
                webbrowser.open(f"file://{html_path}")
            except Exception as e:
                _LOG.debug("Could not open browser: %s", e)
        return result

    def compare_strategies(
        self,
        symbols: list[str],
        strategies: list[str] | None = None,
        lookback_days: int = 365,
    ) -> pl.DataFrame:
        """
        Run all strategies on the same data; return comparison table.

        Returns:
            DataFrame with columns: strategy, sharpe, max_dd, win_rate, profit_factor, approved.
        """
        from datetime import datetime, timedelta

        if strategies is None:
            strategies = ["momentum", "mean_reversion"]
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        rows: list[dict[str, object]] = []
        for strategy in strategies:
            result = self.pipeline.run(
                symbols=symbols,
                timeframe="1d",
                start_date=start_str,
                end_date=end_str,
                strategy_name=strategy,
            )
            ts = result.tearsheet
            rows.append({
                "strategy": strategy,
                "sharpe": ts.sharpe_ratio,
                "max_dd": ts.max_drawdown,
                "win_rate": ts.win_rate,
                "profit_factor": ts.profit_factor,
                "approved": result.approved_for_deployment,
            })
        return pl.DataFrame(rows)

    def deploy_best(self, comparison: pl.DataFrame, symbols: list[str] | None = None) -> str:
        """
        Pick best approved strategy from compare_strategies output, re-run pipeline, write config.

        Returns:
            Path to written config file.
        """
        approved = comparison.filter(pl.col("approved") == True)
        if approved.is_empty():
            raise ValueError("No approved strategy in comparison table.")
        best = approved.sort("sharpe", descending=True).head(1)
        strategy = str(best["strategy"][0])
        from datetime import datetime, timedelta
        end = datetime.now()
        start = end - timedelta(days=365)
        result = self.pipeline.run(
            symbols=symbols or ["BTC/USDT"],
            timeframe="1d",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            strategy_name=strategy,
        )
        if not result.approved_for_deployment:
            raise ValueError("Best strategy run did not pass approval gate; cannot deploy.")
        return self.deployment.from_research_result(result, target="paper")

    def live_inspect(self, tracker: PerformanceTracker) -> dict[str, float]:
        """Return current live metrics from PerformanceTracker for side-by-side with baseline."""
        return tracker.to_dict()
