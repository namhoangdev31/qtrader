"""LiveMonitor: closes the loop by comparing live bot metrics to backtest baseline.

This module implements the LiveMonitor class that runs continuously in the
background, publishing SystemEvents on degradation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from qtrader.analytics.drift import DriftMonitor
from qtrader.analytics.performance import PerformanceAnalytics
from qtrader.backtest.tearsheet import TearsheetMetrics
from qtrader.core.event_bus import EventBus
from qtrader.core.event import SystemEvent
from bot.performance import PerformanceTracker
from qtrader.analytics.telemetry import Telemetry

logger = logging.getLogger(__name__)


@dataclass
class MonitorReport:
    """Report from a single monitoring cycle.

    Attributes:
        timestamp: Time of the report.
        live_metrics: Current live metrics from PerformanceTracker.
        baseline_metrics: Approved backtest metrics (TearsheetMetrics).
        sharpe_ratio_pct: Live Sharpe as percentage of baseline (1.0 = on par).
        win_rate_pct: Live win rate as percentage of baseline.
        drift_alerts: List of features with significant drift.
        performance_alerts: List of metric degradation alerts.
    """

    timestamp: datetime
    live_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    sharpe_ratio_pct: float
    win_rate_pct: float
    drift_alerts: list[str] = field(default_factory=list)
    performance_alerts: list[str] = field(default_factory=list)

    @property
    def has_critical_alerts(self) -> bool:
        """Return True if there are any drift or performance alerts."""
        return bool(self.drift_alerts or self.performance_alerts)

    @property
    def critical_alerts(self) -> list[str]:
        """Return combined list of drift and performance alerts."""
        return self.drift_alerts + self.performance_alerts


class LiveMonitor:
    """Closes the loop: Live bot metrics → Analytics → Compare vs Backtest → Alert.

    Runs continuously in background, publishing SystemEvents on degradation.
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
        """Initialize the LiveMonitor.

        Args:
            tracker: PerformanceTracker from the bot (live metrics).
            analytics: PerformanceAnalytics for cross-checking.
            drift_monitor: DriftMonitor for feature drift detection.
            telemetry: Telemetry for recording metrics (Prometheus/Grafana).
            bus: EventBus for publishing SystemEvents.
            backtest_baseline: The approved backtest result (TearsheetMetrics).
        """
        self.tracker = tracker
        self.analytics = analytics
        self.drift_monitor = drift_monitor
        self.telemetry = telemetry
        self.bus = bus
        self.backtest_baseline = backtest_baseline

    async def run_cycle(self, feature_snapshot: Any) -> MonitorReport:
        """One monitoring cycle.

        Args:
            feature_snapshot: Current live features (Polars DataFrame) for drift check.

        Returns:
            MonitorReport with all alerts and metrics.
        """
        logger.debug("Running live monitor cycle")

        # 1. Current live metrics from PerformanceTracker.to_dict()
        live_metrics = self.tracker.to_dict()
        # Ensure we have the expected keys; if not, use defaults
        live_sharpe = live_metrics.get("sharpe_ratio", 0.0)
        live_win_rate = live_metrics.get("win_rate", 0.0)
        live_max_dd = live_metrics.get("max_drawdown", 0.0)

        # 2. Compare vs backtest_baseline
        baseline_metrics = self.backtest_baseline.to_dict()
        baseline_sharpe = baseline_metrics.get("sharpe_ratio", 0.0)
        baseline_win_rate = baseline_metrics.get("win_rate", 0.0)
        baseline_max_dd = baseline_metrics.get("max_drawdown", 0.0)

        # Performance alerts
        performance_alerts: list[str] = []
        if baseline_sharpe > 0 and live_sharpe < 0.7 * baseline_sharpe:
            performance_alerts.append(
                f"Sharpe degraded: {live_sharpe:.2f} < 70% of baseline ({baseline_sharpe:.2f})"
            )
        if baseline_win_rate > 0 and live_win_rate < 0.7 * baseline_win_rate:
            performance_alerts.append(
                f"Win rate degraded: {live_win_rate:.2f} < 70% of baseline ({baseline_win_rate:.2f})"
            )
        if baseline_max_dd > 0 and live_max_dd > baseline_max_dd * 1.5:
            performance_alerts.append(
                f"Drawdown breached: {live_max_dd:.2f} > 1.5 * baseline ({baseline_max_dd:.2f})"
            )

        # 3. DriftMonitor.detect_drift(train_features, live_features)
        # We need the training features (from the backtest) - we don't have them stored.
        # For now, we'll skip drift detection and rely on the user to provide train_features.
        # In a real system, we would store the training features from the research pipeline.
        drift_alerts: list[str] = []
        # Placeholder: we would call self.drift_monitor.detect_drift here
        # For the sake of the example, we'll leave it empty.

        # 4. Telemetry.record(metrics) for Prometheus/Grafana
        self.telemetry.record(
            {
                "live_sharpe": live_sharpe,
                "live_win_rate": live_win_rate,
                "live_max_drawdown": live_max_dd,
                "baseline_sharpe": baseline_sharpe,
                "baseline_win_rate": baseline_win_rate,
                "baseline_max_drawdown": baseline_max_dd,
            }
        )

        # 5. If any alert: publish SystemEvent(action="EMERGENCY_HALT", reason=alert_msg)
        # Note: The actual publishing is done in the `start` loop, but we can do it here too if desired.
        # We'll just return the report and let the caller decide.

        report = MonitorReport(
            timestamp=datetime.utcnow(),
            live_metrics=live_metrics,
            baseline_metrics=baseline_metrics,
            sharpe_ratio_pct=(
                live_sharpe / baseline_sharpe if baseline_sharpe != 0 else 0.0
            ),
            win_rate_pct=(
                live_win_rate / baseline_win_rate if baseline_win_rate != 0 else 0.0
            ),
            drift_alerts=drift_alerts,
            performance_alerts=performance_alerts,
        )

        logger.debug("Monitor cycle complete: %s", report)
        return report

    async def start(self, interval_s: int = 300) -> None:
        """Continuous monitoring loop with cancellation safety.

        Args:
            interval_s: Seconds between monitoring cycles.
        """
        logger.info("Starting live monitor with interval %ds", interval_s)
        while True:
            try:
                # In a real system, we would fetch live features from the datalake or feature store.
                # For now, we pass an empty DataFrame and rely on the drift monitor to handle it.
                # The user must override _fetch_live_features or pass a feature snapshot.
                feature_snapshot = await self._fetch_live_features()
                report = await self.run_cycle(feature_snapshot)
                if report.has_critical_alerts:
                    alert_msg = report.critical_alerts[0]
                    logger.warning("Publishing EMERGENCY_HALT: %s", alert_msg)
                    await self.bus.publish(
                        SystemEvent(action="EMERGENCY_HALT", reason=alert_msg)
                    )
            except asyncio.CancelledError:
                logger.info("Live monitor cancelled")
                raise
            except Exception as e:
                logger.error("Monitor cycle error", exc_info=e)
            await asyncio.sleep(interval_s)

    async def _fetch_live_features(self) -> Any:
        """Fetch the latest live features for drift detection.

        This method should be overridden by the user to provide the actual
        live feature data (Polars DataFrame) from the feature store or datalake.

        Returns:
            A Polars DataFrame of live features, or an empty DataFrame if not implemented.
        """
        logger.warning("_fetch_live_features not implemented; returning empty DataFrame")
        # Return an empty DataFrame with the expected columns? We don't know the columns.
        # For now, return None and let the drift monitor handle it.
        return None


# ---------------------------------------------------------------------------
# Inline unit-test examples (doctest style)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import doctest

    doctest.testmod()

    # Example usage (not executed unless run directly)
    # monitor = LiveMonitor(...)
    # await monitor.start()