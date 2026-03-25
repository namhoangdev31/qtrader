import asyncio

import pytest

from qtrader.monitoring.metrics import MetricsAggregator
from qtrader.monitoring.warroom_service import WarRoomService

# Constants for verification
INITIAL_NAV = 1000000.0
LOWER_NAV = 950000.0
HIGHER_NAV = 1050000.0
SAMPLE_LATENCY = 50.0
HIGH_LATENCY = 150.0
AVG_LATENCY = 100.0
FILL_LATENCY = 200.0
UPDATE_INTERVAL = 0.1
DRAWDOWN_5PCT = 0.05
VAR_MIN_SAMPLES = 25
NAV_STEP = 1000.0


def test_metrics_aggregator_pnl() -> None:
    """Verify PnL and Drawdown math in MetricsAggregator."""
    agg = MetricsAggregator()

    # Initial update
    agg.update_pnl(nav=INITIAL_NAV)
    assert agg.pnl.total_pnl == 0.0
    assert agg.risk.max_drawdown == 0.0

    # Drawdown case
    agg.update_pnl(nav=LOWER_NAV)
    assert agg.pnl.total_pnl == (LOWER_NAV - INITIAL_NAV)
    assert agg.risk.current_drawdown == DRAWDOWN_5PCT
    assert agg.risk.max_drawdown == DRAWDOWN_5PCT

    # Recovery case
    agg.update_pnl(nav=HIGHER_NAV)
    assert agg.pnl.total_pnl == (HIGHER_NAV - INITIAL_NAV)
    assert agg.risk.current_drawdown == 0.0
    assert agg.risk.max_drawdown == DRAWDOWN_5PCT


def test_metrics_aggregator_latency() -> None:
    """Verify latency tracking."""
    agg = MetricsAggregator()

    agg.record_latency("ack", SAMPLE_LATENCY)
    agg.record_latency("ack", HIGH_LATENCY)
    assert agg.latency.avg_ack_latency == AVG_LATENCY
    assert agg.latency.last_update_ms == HIGH_LATENCY

    agg.record_latency("fill", FILL_LATENCY)
    assert agg.latency.avg_fill_latency == FILL_LATENCY


def test_metrics_aggregator_var() -> None:
    """Verify VaR calculation once window is sufficient."""
    agg = MetricsAggregator(window_size=100)

    # Push declining returns to trigger a negative VaR (loss risk)
    for i in range(VAR_MIN_SAMPLES):
        agg.update_pnl(nav=INITIAL_NAV - i * NAV_STEP)

    assert agg.risk.var_95 != 0.0
    assert agg.risk.var_95 < 0.0


@pytest.mark.asyncio
async def test_warroom_service_lifecycle() -> None:
    """Verify WarRoomService event processing and lifecycle."""
    service = WarRoomService(update_interval_s=UPDATE_INTERVAL)
    await service.start()

    # Push events
    service.push_event("pnl_update", {"nav": INITIAL_NAV, "realized": 0.0})
    service.push_event("latency_record", {"stage": "ack", "latency_ms": SAMPLE_LATENCY})

    # Wait for processing
    await asyncio.sleep(UPDATE_INTERVAL * 2)

    snapshot = service.get_dashboard_snapshot()
    assert snapshot["pnl"]["total"] == 0.0
    assert snapshot["latency"]["avg_ack"] == SAMPLE_LATENCY

    health = service.get_health()
    assert health["status"] == "healthy"

    await service.stop()
    health = service.get_health()
    assert health["status"] == "stopped"


def test_warroom_service_snapshot_fallback() -> None:
    """Verify snapshot fallback when no periodic update has run."""
    service = WarRoomService()
    snapshot = service.get_dashboard_snapshot()
    assert "timestamp" in snapshot
    assert snapshot["pnl"]["total"] == 0.0
