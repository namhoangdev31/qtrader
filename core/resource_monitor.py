"""System resource monitoring and adaptive throttling for latency/memory control."""
import asyncio
import psutil
import logging
import time
from collections import deque
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ResourceThresholds:
    max_cpu_percent: float = 80.0
    max_memory_mb: float = 1024.0
    max_latency_ms: float = 100.0  # event loop latency in milliseconds

class ResourceMonitor:
    """Monitors system resources and provides adaptive throttling."""
    
    def __init__(self, 
                 thresholds: Optional[ResourceThresholds] = None,
                 window_size: int = 300):  # 5 minutes of 1-second samples
        self.thresholds = thresholds or ResourceThresholds()
        self.window_size = window_size
        
        # Rolling windows for metrics
        self._cpu_window: deque = deque(maxlen=window_size)
        self._memory_window: deque = deque(maxlen=window_size)
        self._latency_window: deque = deque(maxlen=window_size)
        
        # Monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_monitoring = False
        
        # Callback lists for different actions
        self._throttle_callbacks: List[Callable] = []
        self._drop_signal_callbacks: List[Callable] = []
        self._warning_callbacks: List[Callable] = []
        
        # Last loop time for latency calculation
        self._last_loop_time: Optional[float] = None

    async def start_monitoring(self):
        """Start background resource monitoring task."""
        if self._is_monitoring:
            return
        self._is_monitoring = True
        self._last_loop_time = time.time()
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("Resource monitoring started")
        
    async def stop_monitoring(self):
        """Stop background resource monitoring."""
        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Resource monitoring stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop that checks resources and triggers throttling."""
        while self._is_monitoring:
            try:
                # Record start time for latency calculation
                loop_start = time.time()
                
                # Collect metrics
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                
                # Calculate loop latency (time since last iteration)
                if self._last_loop_time is not None:
                    actual_interval = loop_start - self._last_loop_time
                    expected_interval = 1.0  # We sleep for 1 second below
                    latency_ms = (actual_interval - expected_interval) * 1000.0
                    # Latency can be negative if we woke up early, but we're interested in positive delays
                    latency_ms = max(0.0, latency_ms)
                else:
                    latency_ms = 0.0
                self._last_loop_time = loop_start
                
                # Add to rolling windows
                self._cpu_window.append(cpu_percent)
                self._memory_window.append(memory_mb)
                self._latency_window.append(latency_ms)
                
                # Compute window averages
                avg_cpu = sum(self._cpu_window) / len(self._cpu_window) if self._cpu_window else 0.0
                avg_memory = sum(self._memory_window) / len(self._memory_window) if self._memory_window else 0.0
                avg_latency = sum(self._latency_window) / len(self._latency_window) if self._latency_window else 0.0
                
                # Check thresholds against window averages
                triggered = False
                reason_parts = []
                
                if avg_cpu > self.thresholds.max_cpu_percent:
                    triggered = True
                    reason_parts.append(f"CPU: {avg_cpu:.1f}% > {self.thresholds.max_cpu_percent}%")
                    
                if avg_memory > self.thresholds.max_memory_mb:
                    triggered = True
                    reason_parts.append(f"Memory: {avg_memory:.1f}MB > {self.thresholds.max_memory_mb}MB")
                    
                if avg_latency > self.thresholds.max_latency_ms:
                    triggered = True
                    reason_parts.append(f"Latency: {avg_latency:.1f}ms > {self.thresholds.max_latency_ms}ms")
                
                if triggered:
                    reason = "; ".join(reason_parts)
                    logger.warning(f"Resource threshold breached: {reason}")
                    await self._trigger_actions(reason, {
                        "cpu": avg_cpu,
                        "memory": avg_memory,
                        "latency": avg_latency
                    })
                
                # Sleep until next interval (aim for 1 second intervals)
                await asyncio.sleep(max(0, 1.0 - (time.time() - loop_start)))
                
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(5.0)  # Back off on error
    
    def register_throttle_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register a callback to be executed when throttling is triggered (for processing throttling)."""
        self._throttle_callbacks.append(callback)
        
    def register_drop_signal_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register a callback to be executed when throttling is triggered (for dropping low-priority signals)."""
        self._drop_signal_callbacks.append(callback)
        
    def register_warning_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register a callback to be executed when throttling is triggered (for warnings/alerts)."""
        self._warning_callbacks.append(callback)
        
    async def _trigger_actions(self, reason: str, metrics: Dict[str, float]):
        """Execute all registered callback groups."""
        logger.info(f"Triggering resource actions due to: {reason}")
        
        # Execute throttle callbacks (for processing throttling)
        for callback in self._throttle_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason, metrics)
                else:
                    callback(reason, metrics)
            except Exception as e:
                logger.error(f"Error in throttle callback: {e}")
                
        # Execute drop signal callbacks (for dropping low-priority signals)
        for callback in self._drop_signal_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason, metrics)
                else:
                    callback(reason, metrics)
            except Exception as e:
                logger.error(f"Error in drop signal callback: {e}")
                
        # Execute warning callbacks (for logging/alerts)
        for callback in self._warning_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason, metrics)
                else:
                    callback(reason, metrics)
            except Exception as e:
                logger.error(f"Error in warning callback: {e}")

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current rolling window metrics."""
        return {
            "cpu": {
                "current": self._cpu_window[-1] if self._cpu_window else 0.0,
                "average": sum(self._cpu_window) / len(self._cpu_window) if self._cpu_window else 0.0,
                "window": list(self._cpu_window)
            },
            "memory": {
                "current": self._memory_window[-1] if self._memory_window else 0.0,
                "average": sum(self._memory_window) / len(self._memory_window) if self._memory_window else 0.0,
                "window": list(self._memory_window)
            },
            "latency": {
                "current": self._latency_window[-1] if self._latency_window else 0.0,
                "average": sum(self._latency_window) / len(self._latency_window) if self._latency_window else 0.0,
                "window": list(self._latency_window)
            }
        }