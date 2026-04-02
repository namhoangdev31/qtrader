import statistics
import time

import pytest

from qtrader.monitoring.metrics_collector import MetricsCollector


@pytest.fixture
def collector():
    registry = {
        "metrics": {
            "execution_latency": {"type": "summary", "unit": "ms"},
            "ticks_total": {"type": "counter", "unit": "count"},
            "drawdown": {"type": "gauge", "unit": "base"}
        }
    }
    return MetricsCollector(registry)

def test_metrics_collector_counter(collector):
    # Record ticks
    collector.record_counter("ticks_total", 50.0)
    collector.record_counter("ticks_total", 10.0)
    
    # Assert monotonic increase
    report = collector.flush_report()
    assert report["counters"]["ticks_total"] == 60.0

def test_metrics_collector_gauge(collector):
    # Update drawdown
    collector.record_gauge("drawdown", 1000.5)
    collector.record_gauge("drawdown", 500.0) # Lowered
    
    # Assert latest snapshot
    report = collector.flush_report()
    assert report["gauges"]["drawdown"] == 500.0

def test_metrics_collector_summary_stats(collector):
    # Record 100 latencies (1 to 100 ms)
    for i in range(1, 101):
        collector.record_summary("execution_latency", float(i))
        
    stats = collector.get_stats("execution_latency")
    
    # Assert statistical accuracy
    assert stats["avg"] == 50.5
    assert stats["min"] == 1.0
    assert stats["max"] == 100.0
    assert stats["p50"] == 51.0 # median
    assert stats["p99"] == 100.0
    assert stats["count"] == 100

def test_metrics_collector_thread_safe(collector):
    # High-concurrency update stress test
    import threading
    
    def worker():
        for _ in range(1000):
            collector.record_counter("stress_ticks")
            
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    report = collector.flush_report()
    assert report["counters"]["stress_ticks"] == 10000
