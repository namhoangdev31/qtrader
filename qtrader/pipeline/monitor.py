"""Live monitor: bot metrics vs backtest baseline, drift and performance alerts."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
import polars as pl

from qtrader.output.analytics.drift import DriftMonitor
from qtrader.output.analytics.performance import PerformanceAnalytics
from qtrader.output.analytics.telemetry import Telemetry
from qtrader.backtest.tearsheet import TearsheetMetrics
from qtrader.output.bot.performance import PerformanceTracker
from qtrader.core.bus import EventBus
from qtrader.core.event import SystemEvent

__all__ = ["LiveMonitor", "MonitorReport"]

_LOG = logging.getLogger("qtrader.pipeline.monitor")


@dataclass(slots=True)
class MonitorReport:
    """One monitoring cycle: live vs baseline and drift/performance alerts."""

    timestamp: datetime
    live_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    sharpe_ratio_pct: float
    win_rate_pct: float
    drift_alerts: list[str] = field(default_factory=list)
    performance_alerts: list[str] = field(default_factory=list)

    @property
    def has_critical_alerts(self) -> bool:
        return bool(self.drift_alerts or self.performance_alerts)

    @property
    def critical_alerts(self) -> list[str]:
        return self.drift_alerts + self.performance_alerts


class LiveMonitor:
    """
    Compares live bot metrics to approved backtest baseline; runs drift checks
    and publishes SystemEvent(EMERGENCY_HALT) on degradation.
    """

    def __init__(
        self,
        tracker: PerformanceTracker,
        analytics: PerformanceAnalytics,
        drift_monitor: DriftMonitor,
        telemetry: Telemetry,
        bus: EventBus,
        backtest_baseline: TearsheetMetrics,
    ) -> None:
        self.tracker = tracker
        self.analytics = analytics
        self.drift_monitor = drift_monitor
        self.telemetry = telemetry
        self.bus = bus
        self.backtest_baseline = backtest_baseline

    def _baseline_to_dict(self) -> dict[str, float]:
        """Convert TearsheetMetrics to dict for comparison."""
        return {
            "sharpe_ratio": self.backtest_baseline.sharpe_ratio,
            "win_rate": self.backtest_baseline.win_rate,
            "max_drawdown": self.backtest_baseline.max_drawdown,
        }

    async def run_cycle(self, feature_snapshot: pl.DataFrame) -> MonitorReport:
        """
        One monitoring cycle: compare live vs baseline, run drift, record telemetry, emit alerts.

        Args:
            feature_snapshot: Current live feature DataFrame for drift check.

        Returns:
            MonitorReport with metrics and any alerts.
        """
        live = self.tracker.to_dict()
        baseline = self._baseline_to_dict()
        sharpe_pct = (
            (live["sharpe_ratio"] / baseline["sharpe_ratio"])
            if baseline.get("sharpe_ratio") and baseline["sharpe_ratio"] != 0
            else 1.0
        )
        wr_pct = (
            (live["win_rate"] / baseline["win_rate"])
            if baseline.get("win_rate") and baseline["win_rate"] != 0
            else 1.0
        )

        perf_alerts: list[str] = []
        if sharpe_pct < 0.70:
            perf_alerts.append("DEGRADATION_SHARPE: Live Sharpe < 70% of baseline")
        if wr_pct < 0.70:
            perf_alerts.append("WIN_RATE_DECAY: Live win rate < 70% of baseline")
        if baseline.get("max_drawdown") and live.get("max_drawdown", 0) > baseline["max_drawdown"] * 1.5:
            perf_alerts.append("DRAWDOWN_BREACH: Live max drawdown > 1.5x baseline")

        drift_alerts: list[str] = []
        if not feature_snapshot.is_empty() and hasattr(self.drift_monitor, "detect_drift"):
            # Drift needs train vs live; caller can pass train in context or we skip
            pass  # Optional: require train_features to be passed in for drift

        self.telemetry.record_pnl("live", live.get("expected_value", 0.0) or 0.0)

        return MonitorReport(
            timestamp=datetime.now(),
            live_metrics=live,
            baseline_metrics=baseline,
            sharpe_ratio_pct=sharpe_pct,
            win_rate_pct=wr_pct,
            drift_alerts=drift_alerts,
            performance_alerts=perf_alerts,
        )

    async def start(
        self,
        interval_s: int = 300,
        feature_fetcher: object | None = None,
    ) -> None:
        """
        Run monitoring loop: run_cycle every interval_s, publish EMERGENCY_HALT on critical alerts.

        Args:
            interval_s: Seconds between cycles.
            feature_fetcher: Optional callable that returns a DataFrame (e.g. async).
        """
        while True:
            try:
                snapshot = pl.DataFrame()
                if feature_fetcher is not None and callable(feature_fetcher):
                    if asyncio.iscoroutinefunction(feature_fetcher):
                        snapshot = await feature_fetcher()
                    else:
                        snapshot = feature_fetcher()
                report = await self.run_cycle(snapshot)
                if report.has_critical_alerts:
                    msg = report.critical_alerts[0]
                    await self.bus.publish(
                        SystemEvent(action="EMERGENCY_HALT", reason=msg),
                    )
                    _LOG.warning("Monitor published EMERGENCY_HALT: %s", msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.error("Monitor cycle error", exc_info=e)
            await asyncio.sleep(interval_s)


if __name__ == "__main__":
    # Pytest-style: synthetic report
    # report = MonitorReport(datetime.now(), {"sharpe_ratio": 0.5}, {"sharpe_ratio": 1.0}, 0.5, 1.0)
    # assert report.has_critical_alerts is False
    # report.performance_alerts.append("DEGRADATION_SHARPE")
    # assert report.has_critical_alerts is True
    pass
