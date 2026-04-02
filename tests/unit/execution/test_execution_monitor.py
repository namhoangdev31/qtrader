import time

import pytest

from qtrader.execution.execution_monitor import LiveExecutionMonitor


@pytest.fixture
def monitor() -> LiveExecutionMonitor:
    """Initialize a LiveExecutionMonitor for institutional execution certification."""
    return LiveExecutionMonitor()


def test_monitor_slippage_buy_adverse(monitor: LiveExecutionMonitor) -> None:
    """Verify that fill price above order price results in adverse slippage for BUY."""
    # Side: BUY (1.0). Order 100. Fill 101.
    # S = 1.0 * (100 - 101) = -1.0.
    order = {"strategy_id": "STRAT_A", "side": "BUY", "price": 100.0, "quantity": 10}
    fill = {"price": 101.0, "quantity": 10}

    report = monitor.update_metrics(order, fill)
    assert report["metrics"]["absolute_execution_slippage"] == -1.0
    assert report["forensics"]["slippage_bps"] == -100.0


def test_monitor_slippage_sell_adverse(monitor: LiveExecutionMonitor) -> None:
    """Verify that fill price below order price results in adverse slippage for SELL."""
    # Side: SELL (-1.0). Order 100. Fill 99.
    # S = -1.0 * (100 - 99) = -1.0.
    order = {"strategy_id": "STRAT_A", "side": "SELL", "price": 100.0, "quantity": 10}
    fill = {"price": 99.0, "quantity": 10}

    report = monitor.update_metrics(order, fill)
    assert report["metrics"]["absolute_execution_slippage"] == -1.0
    assert report["forensics"]["slippage_bps"] == -100.0


def test_monitor_latency_calibration(monitor: LiveExecutionMonitor) -> None:
    """Verify sub-millisecond precision for execution latency tracking."""
    t_now = time.time()
    order = {"strategy_id": "STRAT_A", "timestamp": t_now}
    fill = {"timestamp": t_now + 0.05}  # 50ms latency

    report = monitor.update_metrics(order, fill)
    assert report["metrics"]["recorded_latency_ms"] == pytest.approx(50.0)


def test_monitor_partial_fill_rate(monitor: LiveExecutionMonitor) -> None:
    """Verify fill rate calculation for partial vs. full fills."""
    # Sub 100. Fill 50. Fill rate 0.5.
    order = {"strategy_id": "STRAT_B", "quantity": 100.0}
    fill = {"quantity": 50.0}

    report = monitor.update_metrics(order, fill)
    assert report["metrics"]["strategy_level_fill_rate"] == 0.5


def test_monitor_telemetry_tracking(monitor: LiveExecutionMonitor) -> None:
    """Verify situational awareness and execution forensics telemetry indexing."""
    # Shared order template for Strat_C validation.
    base = {"strategy_id": "STRAT_C", "side": "BUY", "price": 100.0, "quantity": 10}

    order1 = {**base, "timestamp": 100}
    fill1 = {"price": 101.0, "quantity": 10, "timestamp": 100.01}  # 10ms

    order2 = {**base, "timestamp": 200}
    fill2 = {"price": 100.0, "quantity": 10, "timestamp": 200.02}  # 20ms

    monitor.update_metrics(order1, fill1)
    monitor.update_metrics(order2, fill2)

    stats = monitor.get_execution_telemetry("STRAT_C")
    assert stats["avg_slippage_observed"] == -0.5
    assert stats["avg_latency_observed_ms"] == 15.0
    assert stats["cumulative_fill_rate_pct"] == 100.0
    assert stats["total_execution_events"] == 2
