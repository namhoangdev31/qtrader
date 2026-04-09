from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from loguru import logger

from qtrader.core.trace_authority import TraceAuthority

F = TypeVar("F", bound=Callable[..., Any])


def execution_wrapper(source: str) -> Callable[[F], F]:

    def decorator(func: F) -> F:

        @functools.wraps(func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            trace_id = TraceAuthority.generate()
            if args and hasattr(args[0], "get"):
                trace_id = args[0].get("trace_id", trace_id)
            elif args and hasattr(args[0], "trace_id"):
                trace_id = getattr(args[0], "trace_id", trace_id)
            log = logger.bind(trace_id=trace_id, source=source)
            start_time = time.time()
            instance = args[0] if args else None
            fail_fast_engine = getattr(instance, "fail_fast_engine", None)
            try:
                result = await func(*args, **kwargs)
                latency = (time.time() - start_time) * 1000
                log.debug(f"EXECUTION_SUCCESS | {source} | Latency: {latency:.2f}ms")
                return result
            except Exception as e:
                log.error(f"EXECUTION_FAILURE | {source} | Error: {e}")
                if fail_fast_engine:
                    await fail_fast_engine.handle_error(source=source, error=e)
                else:
                    raise e

        return cast("F", async_wrapped)

    return decorator
