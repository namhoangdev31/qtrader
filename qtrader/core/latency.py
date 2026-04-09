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
LATENCY_MAX_MS = 100.0
INTERNAL_HOTSPOT_MAX_MS = 1.0


@dataclass
class LatencyReport:
    tag: str
    duration_ms: float
    is_breach: bool
    threshold: float


class LatencyEnforcer:
    @staticmethod
    def measure(start_time: float, end_time: float) -> float:
        return (end_time - start_time) * 1000.0

    @classmethod
    def check_breach(
        cls, tag: str, start_time: float, threshold: float = LATENCY_MAX_MS
    ) -> LatencyReport:
        duration = cls.measure(start_time, time.perf_counter())
        is_breach = duration > threshold
        if is_breach:
            log.warning(
                f"[LATENCY_BREACH] '{tag}' took {duration:.3f}ms (threshold: {threshold}ms)"
            )
        return LatencyReport(
            tag=tag, duration_ms=duration, is_breach=is_breach, threshold=threshold
        )


def enforce_latency(
    threshold_ms: float = LATENCY_MAX_MS,
) -> Callable[[Callable[P, T]], Callable[P, T]]:

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    LatencyEnforcer.check_breach(func.__name__, start, threshold_ms)

            return async_wrapper
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
    def __init__(self, tag: str, threshold: float = INTERNAL_HOTSPOT_MAX_MS) -> None:
        self.tag = tag
        self.threshold = threshold
        self.start: float = 0.0

    def __enter__(self) -> "latency_context":
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        LatencyEnforcer.check_breach(self.tag, self.start, self.threshold)
