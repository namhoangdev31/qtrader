"""System resource monitoring and adaptive throttling for latency/memory control."""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


@dataclass
class ResourceThresholds:
    max_cpu_percent: float = 80.0
    max_memory_mb: float = 1024.0
    max_latency_ms: float = 100.0  # event loop latency in milliseconds


class ResourceMonitor:
    """Monitors system resources and provides adaptive throttling."""

    def __init__(
        self, thresholds: ResourceThresholds | None = None, window_size: int = 300
    ) -> None:  # 5 minutes of 1-second samples
        self.thresholds = thresholds or ResourceThresholds()
        self.window_size = window_size

        # Rolling windows for metrics
        self._cpu_window: deque = deque(maxlen=window_size)
        self._memory_window: deque = deque(maxlen=window_size)
        self._latency_window: deque = deque(maxlen=window_size)

        # Monitoring task
        self._monitoring_task: asyncio.Task | None = None
        self._is_monitoring = False

        # Callback lists for different actions
        self._throttle_callbacks: list[Callable] = []
        self._drop_signal_callbacks: list[Callable] = []
        self._warning_callbacks: list[Callable] = []

        # Last check time for throttling
        self._last_check_time: float | None = None
        self._last_loop_time: float | None = None

    async def start_monitoring(self) -> None:
        """Start background resource monitoring task."""
        if self._is_monitoring:
            return
        self._is_monitoring = True
        self._last_loop_time = time.time()
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("Resource monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background resource monitoring."""
        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Resource monitoring stopped")

    async def on_market_data(self, event: Any) -> None:
        """Trigger resource check based on market data event (zero latency)."""
        if not self._is_monitoring:
            return

        current_time = time.time()
        # Throttle: Check resources at most once per second to avoid overhead
        if self._last_check_time is not None and current_time - self._last_check_time < 1.0:
            return

        try:
            # Collect metrics (handle missing psutil)
            if psutil is None:
                cpu_percent = 0.0
                memory_mb = 0.0
            else:
                # Use interval=0 for non-blocking check
                cpu_percent = psutil.cpu_percent(interval=None)
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024

            # Latency calculation based on last cycle
            latency_ms = 0.0
            if self._last_check_time is not None:
                latency_ms = max(0.0, (current_time - self._last_check_time - 1.0) * 1000.0)

            self._cpu_window.append(cpu_percent)
            self._memory_window.append(memory_mb)
            self._latency_window.append(latency_ms)
            self._last_check_time = current_time

            # Compute window averages
            avg_cpu = sum(self._cpu_window) / len(self._cpu_window) if self._cpu_window else 0.0
            avg_memory = (
                sum(self._memory_window) / len(self._memory_window) if self._memory_window else 0.0
            )
            avg_latency = (
                sum(self._latency_window) / len(self._latency_window)
                if self._latency_window
                else 0.0
            )

            # Check thresholds
            triggered = False
            reason_parts = []

            if avg_cpu > self.thresholds.max_cpu_percent:
                triggered = True
                reason_parts.append(f"CPU: {avg_cpu:.1f}% > {self.thresholds.max_cpu_percent}%")

            if avg_memory > self.thresholds.max_memory_mb:
                triggered = True
                reason_parts.append(
                    f"Memory: {avg_memory:.1f}MB > {self.thresholds.max_memory_mb}MB"
                )

            if avg_latency > self.thresholds.max_latency_ms:
                triggered = True
                reason_parts.append(
                    f"Latency: {avg_latency:.1f}ms > {self.thresholds.max_latency_ms}ms"
                )

            if triggered:
                reason = "; ".join(reason_parts)
                await self._trigger_actions(
                    reason, {"cpu": avg_cpu, "memory": avg_memory, "latency": avg_latency}
                )
        except Exception as e:
            logger.error(f"Error in resource monitoring: {e}")

    def register_throttle_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Register a callback to be executed when throttling is triggered (for processing throttling)."""
        self._throttle_callbacks.append(callback)

    def register_drop_signal_callback(
        self, callback: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """Register a callback to be executed when throttling is triggered (for dropping low-priority signals)."""
        self._drop_signal_callbacks.append(callback)

    def register_warning_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Register a callback to be executed when throttling is triggered (for warnings/alerts)."""
        self._warning_callbacks.append(callback)

    async def _trigger_actions(self, reason: str, metrics: dict[str, float]) -> None:
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

    def get_current_metrics(self) -> dict[str, Any]:
        """Get current rolling window metrics."""
        return {
            "cpu": {
                "current": self._cpu_window[-1] if self._cpu_window else 0.0,
                "average": sum(self._cpu_window) / len(self._cpu_window)
                if self._cpu_window
                else 0.0,
                "window": list(self._cpu_window),
            },
            "memory": {
                "current": self._memory_window[-1] if self._memory_window else 0.0,
                "average": sum(self._memory_window) / len(self._memory_window)
                if self._memory_window
                else 0.0,
                "window": list(self._memory_window),
            },
            "latency": {
                "current": self._latency_window[-1] if self._latency_window else 0.0,
                "average": sum(self._latency_window) / len(self._latency_window)
                if self._latency_window
                else 0.0,
                "window": list(self._latency_window),
            },
        }
