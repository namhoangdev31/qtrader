from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from loguru import logger

from qtrader.core.trace_authority import TraceAuthority

# To avoid circular imports, we import the engine when needed or use a protocol
# For now, we assume the orchestrator provides the engine or use a global singleton if available

F = TypeVar("F", bound=Callable[..., Any])

def execution_wrapper(source: str) -> Callable[[F], F]:
    """
    Standardizes execution behavior and error handling across the QTrader pipeline.
    
    Provides:
    1. Automatic Trace ID propagation/generation.
    2. Contextual Logger binding.
    3. Failure interception and FailFastEngine escalation.
    4. Latency telemetry.
    
    Args:
        source: The name of the pipeline stage or component (e.g., 'handle_market_data').
        
    Returns:
        Callable: The wrapped function.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            # 1. Trace Propagation Gate
            # Attempt to extract trace_id from first argument if it's a dict/object
            # or generate a new one.
            trace_id = TraceAuthority.generate()
            if args and hasattr(args[0], "get"):
                 trace_id = args[0].get("trace_id", trace_id)
            elif args and hasattr(args[0], "trace_id"):
                 trace_id = getattr(args[0], "trace_id", trace_id)

            log = logger.bind(trace_id=trace_id, source=source)
            start_time = time.time()
            
            # The 'self' instance (usually TradingOrchestrator) is args[0]
            # It MUST have self.fail_fast_engine
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
                    # Deterministic Failure Escalation
                    await fail_fast_engine.handle_error(source=source, error=e)
                else:
                    # Last resort if engine is missing
                    raise e
                    
        return cast("F", async_wrapped)
    return decorator
