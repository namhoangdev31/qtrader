import pytest
import asyncio
from qtrader.hft.optimizer import HFTOptimizer


def test_hft_optimizer_initialization():
    """Test HFTOptimizer initialization with default parameters."""
    optimizer = HFTOptimizer()
    assert optimizer.latency_target_ms == 100.0
    assert optimizer.enable_hft_mode is False
    assert optimizer.is_throttled is False
    assert optimizer.is_safe_mode is False


def test_hft_optimizer_enable_disable_hft():
    """Test enabling and disabling HFT mode."""
    optimizer = HFTOptimizer()

    # Test enabling HFT
    optimizer.enable_hft()
    assert optimizer.enable_hft_mode is True
    # _uvloop_set may be True if uvloop is available and was set, or False if not available
    assert hasattr(optimizer, "_uvloop_set")

    # Test disabling HFT
    optimizer.disable_hft()
    assert optimizer.enable_hft_mode is False


def test_latency_profiler_tracking():
    """Test latency profiling functionality."""
    optimizer = HFTOptimizer()
    profiler = optimizer.latency_profiler

    # Test stage timing
    profiler.start_stage("test_stage")
    import time

    time.sleep(0.001)  # Sleep for 1ms
    latency = profiler.end_stage("test_stage")

    assert latency > 0.0
    assert latency < 100.0  # Should be less than 100ms for 1ms sleep

    # Test latency summary
    summary = profiler.get_latency_summary()
    assert summary["count"] == 1
    assert summary["average_latency_ms"] > 0.0


def test_latency_breakdown():
    """Test latency breakdown functionality."""
    optimizer = HFTOptimizer()
    profiler = optimizer.latency_profiler

    # Add some latency data
    profiler.start_stage("market_data_to_alpha")
    import time

    time.sleep(0.001)
    profiler.end_stage("market_data_to_alpha")

    profiler.start_stage("alpha_to_signal")
    time.sleep(0.002)
    profiler.end_stage("alpha_to_signal")

    # Get breakdown
    breakdown = profiler.get_latency_breakdown()

    assert "market_data_to_alpha" in breakdown
    assert "alpha_to_signal" in breakdown
    assert breakdown["market_data_to_alpha"]["count"] == 1
    assert breakdown["market_data_to_alpha"]["average_ms"] > 0.0
    assert breakdown["alpha_to_signal"]["count"] == 1
    assert breakdown["alpha_to_signal"]["average_ms"] > 0.0


def test_latency_json_logging():
    """Test JSON logging of latency data."""
    optimizer = HFTOptimizer()
    profiler = optimizer.latency_profiler

    # Add some latency data
    profiler.start_stage("test_stage")
    import time

    time.sleep(0.001)
    profiler.end_stage("test_stage")

    # Get JSON log
    json_log = profiler.log_latency_json()
    assert isinstance(json_log, str)
    assert "timestamp" in json_log
    assert "latency_breakdown" in json_log
    assert "overall_summary" in json_log


def test_should_throttle_logic():
    """Test adaptive throttling logic."""
    optimizer = HFTOptimizer(latency_target_ms=100.0)
    optimizer.throttle_threshold_ms = 120.0
    optimizer.baseline_interval_s = 1.0

    # Initially should not throttle
    assert optimizer.should_throttle() is False
    assert optimizer.is_throttled is False

    # Simulate high latency by adding to history
    import time
    from datetime import datetime, timezone

    # Add high latency entries
    for _ in range(10):
        optimizer.latency_profiler.latency_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "test",
                "latency_ms": 130.0,  # Above threshold
            }
        )

    # Now should throttle
    assert optimizer.should_throttle() is True
    assert optimizer.is_throttled is True
    assert optimizer.current_interval_s == 1.5  # baseline * throttle_factor


def test_safe_mode_activation():
    """Test safe mode activation based on latency."""
    optimizer = HFTOptimizer(latency_target_ms=100.0)
    optimizer.safe_mode_latency_ms = 150.0

    # Initially not in safe mode
    assert optimizer.is_safe_mode is False

    # Simulate very high latency
    import time
    from datetime import datetime, timezone

    # Add high latency entries
    for _ in range(10):
        optimizer.latency_profiler.latency_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "test",
                "latency_ms": 160.0,  # Above safe mode threshold
            }
        )

    # Check and update safety mode
    optimizer.check_and_update_safety_mode()
    assert optimizer.is_safe_mode is True

    # Add low latency entries
    optimizer.latency_profiler.latency_history.clear()
    for _ in range(10):
        optimizer.latency_profiler.latency_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "test",
                "latency_ms": 80.0,  # Below safe mode threshold
            }
        )

    # Check and update safety mode - should exit safe mode
    optimizer.check_and_update_safety_mode()
    assert optimizer.is_safe_mode is False


def test_get_adaptive_signal_interval():
    """Test adaptive signal interval calculation."""
    optimizer = HFTOptimizer()
    optimizer.latency_target_ms = 100.0
    optimizer.enable_hft_mode = True

    # Test with no latency history
    interval = optimizer.get_adaptive_signal_interval(base_interval=0.1)
    assert interval == 0.1

    # Add good latency history (below target)
    from datetime import datetime, timezone

    for _ in range(10):
        optimizer.latency_profiler.latency_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "test",
                "latency_ms": 50.0,  # Good latency
            }
        )

    # Should decrease interval (increase frequency)
    interval = optimizer.get_adaptive_signal_interval(base_interval=0.1)
    assert interval < 0.1
    assert interval >= 0.01  # Not too fast

    # Add poor latency history (above target)
    optimizer.latency_profiler.latency_history.clear()
    for _ in range(10):
        optimizer.latency_profiler.latency_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "test",
                "latency_ms": 150.0,  # Poor latency
            }
        )

    # Should increase interval (decrease frequency)
    interval = optimizer.get_adaptive_signal_interval(base_interval=0.1)
    assert interval > 0.1
    assert interval <= 5.0  # Not too slow


def test_performance_report():
    """Test performance report generation."""
    optimizer = HFTOptimizer()

    report = optimizer.get_performance_report()

    assert "hft_mode_enabled" in report
    assert "latency_target_ms" in report
    assert "latency_summary" in report
    assert "latency_breakdown" in report
    assert "uvloop_available" in report
    assert "thread_pool_active" in report
    assert "rolling_windows_count" in report
    assert "throttling_status" in report
    assert "optimizations" in report

    assert isinstance(report["hft_mode_enabled"], bool)
    assert isinstance(report["latency_target_ms"], float)
    assert isinstance(report["latency_summary"], dict)
    assert isinstance(report["latency_breakdown"], dict)
