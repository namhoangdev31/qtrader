from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import qtrader_core

    stats_engine = qtrader_core.StatsEngine()
except ImportError as e:
    _LOG.error(
        "[MONITOR] Institutional Risk Core (qtrader_core) is missing. System startup blocked."
    )
    raise ImportError("qtrader_core is a mandatory dependency for institutional monitoring") from e


@dataclass(slots=True, frozen=True)
class SystemMetrics:
    """
    Industrial Snapshot of Real-Time System Performance.
    """

    pnl_real: float  # Current realized PnL
    pnl_expected: float  # Predicted PnL from the model
    latency_ms: float  # End-to-end execution latency
    slippage_bps: float  # Realized slippage in basis points
    fill_rate: float  # Observed venue fill rate (0.0 to 1.0)


class MonitoringEngine:
    """
    Principal Real-time Monitoring System backed by Rust StatsEngine.

    Objective: Detect degradation in system health and strategic alpha
    before it reaches critical risk thresholds.
    """

    def __init__(
        self,
        pnl_drift_threshold: float = 500.0,
        latency_limit_ms: float = 50.0,
        max_slippage_bps: float = 15.0,
        min_fill_rate: float = 0.90,
        history_window: int = 100,
    ) -> None:
        """
        Initialize the Monitoring Engine parameters.
        """
        self._pnl_thresh = pnl_drift_threshold
        self._lat_limit = latency_limit_ms
        self._slip_thresh = max_slippage_bps
        self._fill_floor = min_fill_rate

        # Performance history for statistical z-score detection
        self._latency_history: list[float] = []
        self._max_history = history_window

        # Telemetry
        self._stats = {"alerts": 0, "evaluations": 0}

    def monitor(self, metrics: SystemMetrics) -> list[str]:
        """
        Continuously evaluate system signals for health degradation via Rust Stats.
        """
        self._stats["evaluations"] += 1
        alerts: list[str] = []

        # 1. PnL Drift Detection
        drift = abs(metrics.pnl_real - metrics.pnl_expected)
        if drift > self._pnl_thresh:
            alerts.append(f"PNL_DRIFT:{drift:.2f}")

        # 2. Latency Anomaly Detection
        if metrics.latency_ms > self._lat_limit:
            alerts.append(f"LATENCY_HARD_LIMIT:{metrics.latency_ms:.2f}ms")

        # Path B: Statistical Z-Score via Rust StatsEngine
        if len(self._latency_history) >= 20:  # noqa: PLR2004
            mu = stats_engine.calculate_mean(self._latency_history)
            sigma = stats_engine.calculate_std(self._latency_history)

            if sigma > 1e-9:
                z_score = stats_engine.calculate_z_score(metrics.latency_ms, mu, sigma)
                if z_score > 3.0:  # noqa: PLR2004
                    alerts.append(f"LATENCY_STAT_ANOMALY:Z={z_score:.2f}")

        # Update History Window
        self._latency_history.append(metrics.latency_ms)
        if len(self._latency_history) > self._max_history:
            self._latency_history.pop(0)

        # 3. Execution Quality Analysis
        if metrics.slippage_bps > self._slip_thresh:
            alerts.append(f"SLIPPAGE_SPIKE:{metrics.slippage_bps:.2f}bps")

        if metrics.fill_rate < self._fill_floor:
            alerts.append(f"FILL_RATE_DROP:{metrics.fill_rate:.2%}")

        # Terminal Alert Logging
        if alerts:
            self._stats["alerts"] += len(alerts)
            for alert in alerts:
                _LOG.warning(f"[ALERT] {alert}")

        return alerts

    def get_health_report(self) -> dict[str, Any]:
        """
        Generate industrial situational awareness report using Rust precision.
        """
        total = self._stats["evaluations"]
        avg_lat = (
            stats_engine.calculate_mean(self._latency_history) if self._latency_history else 0.0
        )
        return {
            "status": "HEALTH_SUMMARY",
            "alert_count": self._stats["alerts"],
            "anomaly_rate": round(self._stats["alerts"] / total, 4) if total > 0 else 0.0,
            "avg_latency_ms": round(avg_lat, 2),
            "engine": "RUST_STATS_CORE",
        }
