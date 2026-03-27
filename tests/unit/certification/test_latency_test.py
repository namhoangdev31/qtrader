import pytest

from qtrader.certification.latency_test import LatencyBenchmarkValidator


@pytest.fixture
def validator() -> LatencyBenchmarkValidator:
    """Initialize a LatencyBenchmarkValidator for institutional performance certification."""
    return LatencyBenchmarkValidator(l_max_ms=50.0)


def test_latency_benchmark_p99_pass(validator: LatencyBenchmarkValidator) -> None:
    """Verify that a latency distribution with P99 < 50ms results in a PASS status."""
    # Mixture of events: 99 events at 42ms, 1 event at 60ms
    latencies = [42.0] * 99 + [60.0]

    report = validator.run_performance_audit(latencies)

    assert report["result"] == "PASS"  # noqa: S101
    assert 42.0 < report["metrics"]["p99_latency_ms"] < 60.0  # noqa: S101, PLR2004
    assert report["metrics"]["mean_latency_ms"] == 42.18  # noqa: S101, PLR2004


def test_latency_benchmark_p99_breach_fail(validator: LatencyBenchmarkValidator) -> None:
    """Verify that a latency distribution with P99 > 50ms results in a FAIL status."""
    # 2 events at 55ms (P99 will be 55ms)
    latencies = [55.0] * 10

    report = validator.run_performance_audit(latencies)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["metrics"]["p99_latency_ms"] == 55.0  # noqa: S101, PLR2004


def test_latency_benchmark_empty_handling(validator: LatencyBenchmarkValidator) -> None:
    """Verify that empty latency sets are handled gracefully."""
    report = validator.run_performance_audit([])

    assert report["result"] == "SKIP"  # noqa: S101
    assert report["status"] == "LATENCY_EMPTY"  # noqa: S101


def test_latency_benchmark_telemetry_tracking(validator: LatencyBenchmarkValidator) -> None:
    """Verify cumulative peak P99 and event count tracking."""
    validator.run_performance_audit([10.0, 20.0, 30.0])  # P99 ~ 29.8
    validator.run_performance_audit([40.0, 50.0, 60.0])  # P99 ~ 59.8

    stats = validator.get_performance_telemetry()
    assert stats["total_benchmark_events"] == 6  # noqa: S101, PLR2004
    assert 59.0 < stats["peak_lifecycle_p99_ms"] < 60.0  # noqa: S101, PLR2004
    assert stats["status"] == "PERFORMANCE_GOVERNANCE"  # noqa: S101


def test_latency_benchmark_jitter_detection(validator: LatencyBenchmarkValidator) -> None:
    """Verify jitter (standard deviation) calculation."""
    # Low jitter
    low_jit = validator.run_performance_audit([10.0, 10.1, 9.9, 10.0])
    # High jitter
    high_jit = validator.run_performance_audit([1.0, 100.0, 1.0, 100.0])

    assert low_jit["metrics"]["stdev_jit_ms"] < 1.0  # noqa: S101
    assert high_jit["metrics"]["stdev_jit_ms"] > 40.0  # noqa: S101, PLR2004
