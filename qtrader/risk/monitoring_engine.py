from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger(__name__)

DEFAULT_PNL_DRIFT_THRESHOLD = 500.0
DEFAULT_LATENCY_LIMIT_MS = 50.0
DEFAULT_MAX_SLIPPAGE_BPS = 15.0
DEFAULT_MIN_FILL_RATE = 0.9
DEFAULT_HISTORY_WINDOW = 100
MIN_HISTORY_STATS = 20
Z_SCORE_THRESHOLD = 3.0
EPSILON = 1e-09
PRECISION_4 = 4
PRECISION_2 = 2
ZERO_FLOAT = 0.0

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
        pnl_drift_threshold: float = DEFAULT_PNL_DRIFT_THRESHOLD,
        latency_limit_ms: float = DEFAULT_LATENCY_LIMIT_MS,
        max_slippage_bps: float = DEFAULT_MAX_SLIPPAGE_BPS,
        min_fill_rate: float = DEFAULT_MIN_FILL_RATE,
        history_window: int = DEFAULT_HISTORY_WINDOW,
    ) -> None:
        self._min_history_stats = MIN_HISTORY_STATS
        self._z_score_threshold = Z_SCORE_THRESHOLD
        self._epsilon = EPSILON
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
        if len(self._latency_history) >= self._min_history_stats:
            mu = stats_engine.calculate_mean(self._latency_history)
            sigma = stats_engine.calculate_std(self._latency_history)
            if sigma > self._epsilon:
                z_score = stats_engine.calculate_z_score(metrics.latency_ms, mu, sigma)
                if z_score > self._z_score_threshold:
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
            stats_engine.calculate_mean(self._latency_history)
            if self._latency_history
            else ZERO_FLOAT
        )
        return {
            "status": "HEALTH_SUMMARY",
            "alert_count": self._stats["alerts"],
            "anomaly_rate": round(self._stats["alerts"] / total, PRECISION_4)
            if total > 0
            else ZERO_FLOAT,
            "avg_latency_ms": round(avg_lat, PRECISION_2),
            "engine": "RUST_STATS_CORE",
        }
