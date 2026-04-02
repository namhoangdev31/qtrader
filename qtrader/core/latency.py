"""Global Latency Enforcer for deterministic trading performance monitoring."""
import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar

log = logging.getLogger("qtrader.core.latency")

T = TypeVar("T")
P = ParamSpec("P")

# Default system-wide threshold for total event processing (Market-to-Fill)
LATENCY_MAX_MS = 100.0
INTERNAL_HOTSPOT_MAX_MS = 1.0

@dataclass
class LatencyReport:
    """Consolidated latency report."""
    tag: str
    duration_ms: float
    is_breach: bool
    threshold: float

class LatencyEnforcer:
    """
    Middleware for measuring and enforcing strict latency constraints across all layers.
    Ensures that critical execution paths do not exceed production performance budgets.
    """
    
    @staticmethod
    def measure(start_time: float, end_time: float) -> float:
        """Calculate and return latency in milliseconds."""
        return (end_time - start_time) * 1000.0

    @classmethod
    def check_breach(cls, tag: str, start_time: float, threshold: float = LATENCY_MAX_MS) -> LatencyReport:
        """Calculate duration and check for breach against a specific threshold."""
        duration = cls.measure(start_time, time.perf_counter())
        is_breach = duration > threshold
        
        if is_breach:
            log.warning(f"[LATENCY_BREACH] '{tag}' took {duration:.3f}ms (threshold: {threshold}ms)")
            
        return LatencyReport(tag=tag, duration_ms=duration, is_breach=is_breach, threshold=threshold)

def enforce_latency(threshold_ms: float = LATENCY_MAX_MS) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to enforce latency on synchronous or asynchronous handlers."""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    LatencyEnforcer.check_breach(func.__name__, start, threshold_ms)
            return async_wrapper  # type: ignore
        else:
            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    LatencyEnforcer.check_breach(func.__name__, start, threshold_ms)
            return sync_wrapper
    return decorator

class latency_context:
    """Context manager for manual block profiling."""
    def __init__(self, tag: str, threshold: float = INTERNAL_HOTSPOT_MAX_MS) -> None:
        self.tag = tag
        self.threshold = threshold
        self.start: float = 0.0

    def __enter__(self) -> 'latency_context':
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        LatencyEnforcer.check_breach(self.tag, self.start, self.threshold)
