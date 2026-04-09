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
    pnl_real: float
    pnl_expected: float
    latency_ms: float
    slippage_bps: float
    fill_rate: float


class MonitoringEngine:
    def __init__(
        self,
        pnl_drift_threshold: float = 500.0,
        latency_limit_ms: float = 50.0,
        max_slippage_bps: float = 15.0,
        min_fill_rate: float = 0.9,
        history_window: int = 100,
    ) -> None:
        self._pnl_thresh = pnl_drift_threshold
        self._lat_limit = latency_limit_ms
        self._slip_thresh = max_slippage_bps
        self._fill_floor = min_fill_rate
        self._latency_history: list[float] = []
        self._max_history = history_window
        self._stats = {"alerts": 0, "evaluations": 0}

    def monitor(self, metrics: SystemMetrics) -> list[str]:
        self._stats["evaluations"] += 1
        alerts: list[str] = []
        drift = abs(metrics.pnl_real - metrics.pnl_expected)
        if drift > self._pnl_thresh:
            alerts.append(f"PNL_DRIFT:{drift:.2f}")
        if metrics.latency_ms > self._lat_limit:
            alerts.append(f"LATENCY_HARD_LIMIT:{metrics.latency_ms:.2f}ms")
        if len(self._latency_history) >= 20:
            mu = stats_engine.calculate_mean(self._latency_history)
            sigma = stats_engine.calculate_std(self._latency_history)
            if sigma > 1e-09:
                z_score = stats_engine.calculate_z_score(metrics.latency_ms, mu, sigma)
                if z_score > 3.0:
                    alerts.append(f"LATENCY_STAT_ANOMALY:Z={z_score:.2f}")
        self._latency_history.append(metrics.latency_ms)
        if len(self._latency_history) > self._max_history:
            self._latency_history.pop(0)
        if metrics.slippage_bps > self._slip_thresh:
            alerts.append(f"SLIPPAGE_SPIKE:{metrics.slippage_bps:.2f}bps")
        if metrics.fill_rate < self._fill_floor:
            alerts.append(f"FILL_RATE_DROP:{metrics.fill_rate:.2%}")
        if alerts:
            self._stats["alerts"] += len(alerts)
            for alert in alerts:
                _LOG.warning(f"[ALERT] {alert}")
        return alerts

    def get_health_report(self) -> dict[str, Any]:
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
