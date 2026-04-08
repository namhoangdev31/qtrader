import pytest

from qtrader.risk.monitoring_engine import MonitoringEngine, SystemMetrics


@pytest.fixture
def engine() -> MonitoringEngine:
    """Initialize MonitoringEngine with industrial defaults (15bps slippage, 50ms latency)."""
    return MonitoringEngine(
        pnl_drift_threshold=500.0, latency_limit_ms=50.0, max_slippage_bps=15.0, min_fill_rate=0.90
    )


def test_monitor_happy_path(engine: MonitoringEngine) -> None:
    """Verify that nominal system metrics trigger no alerts."""
    metrics = SystemMetrics(
        pnl_real=1000.0, pnl_expected=1000.0, latency_ms=25.0, slippage_bps=5.0, fill_rate=0.98
    )
    alerts = engine.monitor(metrics)
    assert len(alerts) == 0


def test_monitor_pnl_drift(engine: MonitoringEngine) -> None:
    """Verify that pnl drift triggers an alert."""
    metrics = SystemMetrics(
        pnl_real=1000.0,
        pnl_expected=1600.0,  # 600.0 > 500.0 threshold
        latency_ms=25.0,
        slippage_bps=5.0,
        fill_rate=0.98,
    )
    alerts = engine.monitor(metrics)
    assert any("PNL_DRIFT" in a for a in alerts)


def test_monitor_latency_hard_limit(engine: MonitoringEngine) -> None:
    """Verify that latency exceeding the hard limit triggers an alert."""
    metrics = SystemMetrics(
        pnl_real=1000.0,
        pnl_expected=1000.0,
        latency_ms=65.0,  # > 50.0 ms limit
        slippage_bps=5.0,
        fill_rate=0.98,
    )
    alerts = engine.monitor(metrics)
    assert any("LATENCY_HARD_LIMIT" in a for a in alerts)


def test_monitor_latency_statistical_anomaly(engine: MonitoringEngine) -> None:
    """Verify that statistical latency anomalies (Z > 3) are detected."""
    # 1. Prime the history with slight variance to avoid sigma=0
    # Window is 100, so let's do 110 to trigger .pop(0)
    for i in range(110):
        # 10.0, 11.0, 10.0, 11.0 ...
        lat = 10.0 + (i % 2)
        engine.monitor(SystemMetrics(1000.0, 1000.0, lat, 5.0, 0.98))

    # 2. Trigger Z-score anomaly (Mu ~ 10.5, Sigma ~ 0.5)
    # Z = (80 - 10.5) / 0.5 = 139 >> 3.0
    metrics = SystemMetrics(1000.0, 1000.0, 80.0, 5.0, 0.98)
    alerts = engine.monitor(metrics)

    assert any("LATENCY_STAT_ANOMALY" in a for a in alerts)
    assert any("LATENCY_HARD_LIMIT" in a for a in alerts)


def test_monitor_execution_degradation(engine: MonitoringEngine) -> None:
    """Verify that high slippage or low fill rate triggers an alert."""
    # Slippage breach (20bps > 15bps)
    m1 = SystemMetrics(1000.0, 1000.0, 25.0, 20.0, 0.98)
    # Fill rate breach (80% < 90%)
    m2 = SystemMetrics(1000.0, 1000.0, 25.0, 5.0, 0.80)

    a1 = engine.monitor(m1)
    a2 = engine.monitor(m2)

    assert any("SLIPPAGE_SPIKE" in a for a in a1)
    assert any("FILL_RATE_DROP" in a for a in a2)


def test_monitor_health_reporting(engine: MonitoringEngine) -> None:
    """Verify industrial telemetry tracking of alerts."""
    # Trigger 2 alerts
    engine.monitor(SystemMetrics(1000.0, 2000.0, 10.0, 5.0, 0.98))  # Pnl drift
    engine.monitor(SystemMetrics(1000.0, 1000.0, 100.0, 5.0, 0.98))  # Latency

    report = engine.get_health_report()
    assert report["alert_count"] == 2
    assert report["anomaly_rate"] == 1.0
