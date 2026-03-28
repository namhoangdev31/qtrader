import time
import pytest
from qtrader.core.latency_monitor import LatencyMonitor, LatencyViolation

@pytest.fixture
def monitor():
    # Fresh monitor for each test
    policy = {
        "budgets": {
            "fast_stage": 5.0,
            "slow_stage": 20.0,
            "total_end_to_end": 100.0 # Standard 100ms SLA
        },
        "rules": {
            "fail_on_breach": True
        }
    }
    return LatencyMonitor(policy)

def test_latency_monitor_within_budget(monitor):
    # Fast stage: 2ms (within 5ms limit)
    monitor.start_stage("fast_stage")
    time.sleep(0.002)
    duration = monitor.end_stage("fast_stage")
    
    assert duration >= 2.0
    assert duration < 5.0
    assert monitor.total_latency_ms == duration

def test_latency_monitor_stage_breach(monitor):
    # Fast stage: 10ms (violates 5ms limit)
    monitor.start_stage("fast_stage")
    time.sleep(0.010)
    
    with pytest.raises(LatencyViolation) as excinfo:
        monitor.end_stage("fast_stage")
    
    assert "Stage='fast_stage' took" in str(excinfo.value)

def test_latency_monitor_total_pipeline_breach(monitor):
    # Two stages that don't violate individual limits (now 50ms) 
    # but total > cumulative limit (30ms total)
    monitor.policy["slow_stage"] = 50.0 # Increase to avoid jitter
    monitor.policy["total_end_to_end"] = 30.0 # Override for total breach test
    
    # Stage 1: 18ms (within 50ms)
    monitor.start_stage("slow_stage")
    time.sleep(0.018)
    monitor.end_stage("slow_stage")
    
    # Stage 2: 18ms (within 50ms) -> Total ~36ms (breaches 30ms total)
    monitor.start_stage("slow_stage")
    time.sleep(0.018)
    
    with pytest.raises(LatencyViolation) as excinfo:
        monitor.end_stage("slow_stage")
        
    assert "Stage='total_pipeline' took" in str(excinfo.value)
    assert "Limit=30.0ms" in str(excinfo.value)

def test_latency_monitor_reset(monitor):
    monitor.start_stage("fast_stage")
    time.sleep(0.002)
    monitor.end_stage("fast_stage")
    assert monitor.total_latency_ms > 0
    
    monitor.reset_pipeline()
    assert monitor.total_latency_ms == 0
    assert len(monitor._timers) == 0
