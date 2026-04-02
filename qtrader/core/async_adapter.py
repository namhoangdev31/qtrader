from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import aiohttp
from loguru import logger

T = TypeVar("T")


class AsyncAdapter:
    """
    Performance Sovereign Authority for Asynchronous Execution.
    Centralizes non-blocking IO resources and event loop management.
    Ensures zero synchronous blocking in critical execution paths.
    """

    _instance: AsyncAdapter | None = None
    _session: aiohttp.ClientSession | None = None

    def __new__(cls) -> AsyncAdapter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_session(self) -> aiohttp.ClientSession:
        """
        Produce a shared, non-blocking HTTP session with optimized pooling.
        """
        if self._session is None or self._session.closed:
            # Optimize connection pooling for low-latency exchange communication
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                use_dns_cache=True,
                family=socket.AF_INET # IPv4 preference for reliability
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30, connect=5)
            )
            logger.info("[ASYNC] Initialized shared high-performance aiohttp session.")
        return self._session

    async def close(self) -> None:
        """Gracefully shutdown asynchronous resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("[ASYNC] Shared HTTP session closed.")

    @staticmethod
    async def run_task(
        coro: Coroutine[Any, Any, T],
        on_error: Callable[[Exception], None] | None = None
    ) -> T | None:
        """
        Execute a coroutine in a non-blocking task with built-in error propagation.
        """
        try:
            return await coro
        except Exception as e:
            logger.error(f"[ASYNC] Critical task failure: {e}")
            if on_error:
                on_error(e)
            return None

    @staticmethod
    def spawn_background_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """
        Fire-and-forget background task management.
        Useful for non-blocking reporting or telemetry persistence.
        """
        task = asyncio.create_task(coro)
        
        # Guard against unhandled background failures
        def _on_done(t: asyncio.Task[Any]) -> None:
            try:
                t.result()
            except asyncio.CancelledError:
                pass
            except Exception as ex:
                logger.error(f"[ASYNC] Background task failed: {ex}")

        task.add_done_callback(_on_done)
        return task


# Global singleton authority
async_authority = AsyncAdapter()
get_session = async_authority.get_session
spawn_task = async_authority.spawn_background_task
