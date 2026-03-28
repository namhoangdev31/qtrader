from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Coroutine, Dict, Optional, TypeVar

from loguru import logger

T = TypeVar("T")


class LockTimeoutError(Exception):
    """Exception raised when a lock acquisition exceeds the safety threshold."""
    pass


class ConcurrencyGuard:
    """
    Sovereign Authority for Concurrency Control.
    Ensures race-free state transitions for shared resources.
    Protects the 100ms latency budget by monitoring lock contention.
    """

    _instance: Optional[ConcurrencyGuard] = None

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._held_since: Dict[str, float] = {}
        self._contention_threshold_ms: float = 50.0 # Critical threshold for a single lock

    @classmethod
    def get_instance(cls) -> ConcurrencyGuard:
        if cls._instance is None:
            cls._instance = ConcurrencyGuard()
        return cls._instance

    async def acquire(self, resource_name: str) -> None:
        """
        Acquire a named lock for a specific shared resource.
        """
        start_time = time.perf_counter()
        
        # We don't use a global timeout here to prevent partial state updates
        # but we monitor the contention.
        await self._locks[resource_name].acquire()
        
        wait_time = (time.perf_counter() - start_time) * 1000
        if wait_time > self._contention_threshold_ms:
             logger.warning(
                 f"[CONCURRENCY] High contention on Resource='{resource_name}': "
                 f"Wait={wait_time:.2f}ms (Limit={self._contention_threshold_ms}ms)"
             )

        self._held_since[resource_name] = time.perf_counter()

    def release(self, resource_name: str) -> None:
        """
        Release a named lock and monitor hold duration.
        """
        if not self._locks[resource_name].locked():
            return

        hold_duration = (time.perf_counter() - self._held_since.get(resource_name, time.perf_counter())) * 1000
        if hold_duration > self._contention_threshold_ms:
             logger.error(
                 f"[CONCURRENCY] Budget Breach: Resource='{resource_name}' held for {hold_duration:.2f}ms. "
                 f"THIS VIOLATES THE 100ms LATENCY SLA."
             )
        
        self._locks[resource_name].release()
        self._held_since.pop(resource_name, None)

    async def safe_execute(self, resource_name: str, coro: Coroutine[Any, Any, T]) -> T:
        """
        Execute a coroutine within a protected resource lock.
        Guarantees release even on failure.
        """
        await self.acquire(resource_name)
        try:
            return await coro
        finally:
            self.release(resource_name)


# Global singleton authority
concurrency_guard = ConcurrencyGuard.get_instance()
safe_update = concurrency_guard.safe_execute
