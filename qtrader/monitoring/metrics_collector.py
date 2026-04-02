from __future__ import annotations

import collections
import statistics
import threading
import time
from collections.abc import Mapping
from typing import Any

from loguru import logger


class MetricsCollector:
    """
    Sovereign Authority for Real-Time Telemetry.
    Collects performance, reliability, and risk indicators for system visibility.
    Enforces the single metrics registry standard.
    """

    _instance: MetricsCollector | None = None
    _lock = threading.Lock()

    def __init__(self, registry: Mapping[str, Any]) -> None:
        self.registry = registry.get("metrics", {})
        self.rules = registry.get("telemetry_governance", {})
        
        # State: Thread-safe metrics storage
        self._counters: dict[str, float] = collections.defaultdict(float)
        self._gauges: dict[str, float] = collections.defaultdict(float)
        self._summaries: dict[str, list[float]] = collections.defaultdict(list)
        
        self._last_flush = time.perf_counter()

    @classmethod
    def get_instance(cls, registry: dict[str, Any] | None = None) -> MetricsCollector:
        if cls._instance is None:
             with cls._lock:
                  if cls._instance is None:
                       if registry is None:
                            # Prototype fallback
                            registry = {"metrics": {}}
                       cls._instance = MetricsCollector(registry)
        return cls._instance

    def record_counter(self, name: str, value: float = 1.0) -> None:
        """Increment a monotonic increasing indicator."""
        with self._lock:
            self._counters[name] += value

    def record_gauge(self, name: str, value: float) -> None:
        """Update an indicator with an absolute current value."""
        with self._lock:
            self._gauges[name] = value

    def record_summary(self, name: str, value: float) -> None:
        """Observe a distribution of values (e.g. latency)."""
        with self._lock:
            self._summaries[name].append(value)
            
            # Retention limit for in-memory summaries (to prevent memory leaks)
            if len(self._summaries[name]) > 10000:
                 self._summaries[name].pop(0)

    def get_stats(self, name: str) -> dict[str, float] | None:
        """Calculate statistics for summaries (avg, p50, p99)."""
        with self._lock:
            values = self._summaries.get(name)
            if not values:
                return None
            
            # Monotonically increasing counter stats
            if name in self._counters:
                 return {"count": self._counters[name]}

            # Summary stats
            sorted_v = sorted(values)
            n = len(sorted_v)
            return {
                "avg": statistics.mean(sorted_v),
                "min": sorted_v[0],
                "max": sorted_v[-1],
                "p50": sorted_v[int(n * 0.5)],
                "p95": sorted_v[int(n * 0.95)],
                "p99": sorted_v[int(n * 0.99)],
                "count": n
            }

    def flush_report(self) -> dict[str, Any]:
        """Produce a comprehensive telemetry snapshot."""
        with self._lock:
            report = {
                "timestamp": time.time(),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "summaries": {k: self.get_stats(k) for k in self._summaries}
            }
            logger.info(f"[METRICS] Flush Complete. TPS={self._counters.get('ticks_total', 0)}")
            return report


# Global singleton authority
metrics_collector = MetricsCollector.get_instance()
