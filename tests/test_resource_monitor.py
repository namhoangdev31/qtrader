#!/usr/bin/env python3
"""Test script for ResourceMonitor."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Test callbacks
throttle_calls = []
drop_signal_calls = []
warning_calls = []

def throttle_callback(reason: str, metrics: dict):
    throttle_calls.append((reason, metrics))
    print(f"[THROTTLE] Triggered: {reason}")

def drop_signal_callback(reason: str, metrics: dict):
    drop_signal_calls.append((reason, metrics))
    print(f"[DROP SIGNAL] Triggered: {reason}")

def warning_callback(reason: str, metrics: dict):
    warning_calls.append((reason, metrics))
    print(f"[WARNING] Triggered: {reason}")

async def test_resource_monitor():
    """Test the resource monitor functionality."""
    # Try to import the required modules
    try:
        from qtrader.core.resource_monitor import ResourceMonitor, ResourceThresholds
        import psutil
    except ImportError:
        print("psutil not available, skipping ResourceMonitor test")
        return
    
    print("Testing ResourceMonitor...")
    
    # Create resource monitor with low thresholds for testing
    thresholds = ResourceThresholds(
        max_cpu_percent=50.0,   # Low threshold to trigger easily
        max_memory_mb=100.0,    # Low threshold
        max_latency_ms=10.0     # Low threshold
    )
    
    monitor = ResourceMonitor(thresholds=thresholds, window_size=10)
    
    # Register callbacks
    monitor.register_throttle_callback(throttle_callback)
    monitor.register_drop_signal_callback(drop_signal_callback)
    monitor.register_warning_callback(warning_callback)
    
    # Start monitoring
    await monitor.start_monitoring()
    
    # Let it run for a few seconds to collect some metrics
    print("Monitoring for 5 seconds...")
    await asyncio.sleep(5)
    
    # Check current metrics
    metrics = monitor.get_current_metrics()
    print(f"\nCurrent metrics:")
    print(f"  CPU: {metrics['cpu']['average']:.1f}% (threshold: {thresholds.max_cpu_percent}%)")
    print(f"  Memory: {metrics['memory']['average']:.1f} MB (threshold: {thresholds.max_memory_mb} MB)")
    print(f"  Latency: {metrics['latency']['average']:.1f} ms (threshold: {thresholds.max_latency_ms} ms)")
    
    # Stop monitoring
    await monitor.stop_monitoring()
    
    # Report callback activity
    print(f"\nCallback activity:")
    print(f"  Throttle callbacks: {len(throttle_calls)}")
    print(f"  Drop signal callbacks: {len(drop_signal_calls)}")
    print(f"  Warning callbacks: {len(warning_calls)}")
    
    if throttle_calls:
        print(f"  Last throttle: {throttle_calls[-1][0]}")
    
    print("\nResourceMonitor test completed!")

if __name__ == "__main__":
    asyncio.run(test_resource_monitor())