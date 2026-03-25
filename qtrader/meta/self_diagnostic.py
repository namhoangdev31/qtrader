from __future__ import annotations

from typing import cast

import polars as pl


class SelfDiagnostic:
    """
    Automated System Diagnostic & Drift Detector.

    Monitors real-time performance against historical baselines. Detects
    alpha decay, execution slippage, or model degradation by analyzing
    rolling Sharpe and PnL statistics. Triggers automated retraining
    alerts to the 'ResearchLoop' when significant drift is detected.

    Conforms to the KILO.AI Industrial Grade Protocol for self-healing
    trading systems.
    """

    @staticmethod
    def detect_degradation(
        performance_history: pl.DataFrame,
        baseline_sharpe: float = 1.0,
        degradation_threshold: float = 0.3,
    ) -> dict[str, bool]:
        """
        Evaluate current health compared to baseline.

        Logic:
        Trigger = (Current_Sharpe < Baseline_Sharpe * (1 - Threshold))

        Args:
            performance_history: Moving metrics with 'timestamp', 'sharpe', 'pnl'.
            baseline_sharpe: The expected Sharpe ratio from backtest/production.
            degradation_threshold: Percentage drop from baseline to trigger alert.

        Returns:
            Dictionary with health status and retraining flags.
        """
        if performance_history.is_empty():
            return {"healthy": True, "trigger_retrain": False}

        # Calculate rolling average sharpe of the most recent window
        # (Assuming last 10 observations represent current state)
        recent_window = 10
        raw_sharpe = performance_history.tail(recent_window)["sharpe"].mean()

        # Guard against nulls from short history
        current_sharpe = cast(float, raw_sharpe) if raw_sharpe is not None else 0.0

        # Degradation condition
        limit = baseline_sharpe * (1.0 - degradation_threshold)
        is_failing = current_sharpe < limit

        return {
            "healthy": not is_failing,
            "trigger_retrain": is_failing,
        }

    @staticmethod
    def monitor_pnl_drawdown(
        pnl_series: pl.Series,
        max_drawdown_limit: float = -5000.0,
    ) -> bool:
        """
        Instantaneous check for dollar-based drawdown violations.

        Args:
            pnl_series: Vectorized cumulative PnL values.
            max_drawdown_limit: Threshold in USD (negative).

        Returns:
            True if system must stop (Critical Failure).
        """
        if pnl_series.is_empty():
            return False

        # Calculate current drawdown from peak
        rolling_max = pnl_series.cum_max()
        drawdown = pnl_series - rolling_max

        # Check against limit
        raw_dd = drawdown.min()
        current_dd = cast(float, raw_dd) if raw_dd is not None else 0.0

        return current_dd <= max_drawdown_limit
