"""System resource monitoring and adaptive throttling for latency/memory control."""
import asyncio
import psutil
import logging
from typing import Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ResourceThresholds:
    max_cpu_percent: float = 80.0
    max_memory_mb: float = 1024.0
    max_latency_ms: float = 100.0

class ResourceMonitor:
    """Monitors system resources and provides adaptive throttling."""
    
    def __init__(self, thresholds: Optional[ResourceThresholds] = None):
        self.thresholds = thresholds or ResourceThresholds()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._throttle_callbacks: list[Callable] = []
        self._is_monitoring = False
        
    async def start_monitoring(self):
        """Start background resource monitoring task."""
        if self._is_monitoring:
            return
        self._is_monitoring = True
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
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                
                # Check thresholds and trigger throttling if needed
                if cpu_percent > self.thresholds.max_cpu_percent:
                    logger.warning(f"High CPU usage: {cpu_percent}%")
                    await self._trigger_throttle("cpu")
                    
                if memory_mb > self.thresholds.max_memory_mb:
                    logger.warning(f"High memory usage: {memory_mb:.2f} MB")
                    await self._trigger_throttle("memory")
                    
                await asyncio.sleep(1.0)  # Check every second
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(5.0)
                
    def register_throttle_callback(self, callback: Callable):
        """Register a callback to be executed when throttling is triggered."""
        self._throttle_callbacks.append(callback)
        
    async def _trigger_throttle(self, reason: str):
        """Execute all registered throttle callbacks."""
        logger.info(f"Triggering throttling due to {reason}")
        for callback in self._throttle_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason)
                else:
                    callback(reason)
            except Exception as e:
                logger.error(f"Error in throttle callback: {e}")