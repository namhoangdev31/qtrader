from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Any, NoReturn
from qtrader.core.container import container
from qtrader.core.exceptions import ConstraintViolation
from qtrader.core.violation_handler import violation_handler

if TYPE_CHECKING:
    from collections.abc import Callable
    from qtrader.core.events import BaseEvent


class EnforcementEngine:
    def __init__(self) -> None:
        self.config = container.get("config")
        self.trace = container.get("trace")
        self.logger = container.get("logger")
        self.failfast = container.get("failfast")
        self.decimal = container.get("decimal")
        self.checks_performed = 0
        self.violations_detected = 0

    async def validate_pre_execution(self, context: dict[str, Any]) -> None:
        if "trace_id" not in context:
            await self._handle_violation("C3", "Missing trace_id in execution context")
        if not hasattr(self, "config") or self.config is None:
            await self._handle_violation("C2", "ConfigManager authority not initialized in engine")
        self.checks_performed += 1

    async def validate_event(self, event: BaseEvent) -> None:
        if not hasattr(event, "trace_id") or not event.trace_id:
            await self._handle_violation("C3", f"Event {type(event).__name__} missing trace_id")
        for field in ["price", "quantity", "strength", "close", "high", "low"]:
            if hasattr(event, field):
                val = getattr(event, field)
                if isinstance(val, float):
                    await self._handle_violation(
                        "C4", f"Floating point value detected in event field: {field}"
                    )
        self.checks_performed += 1

    async def validate_post_execution(self, result: Any) -> None:
        self.checks_performed += 1

    async def _handle_violation(
        self, constraint_id: str, message: str, context: Optional[dict[str, Any]] = None
    ) -> None:
        self.violations_detected += 1
        await violation_handler.handle_violation(
            ConstraintViolation(constraint_id, message), context=context
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "checks": self.checks_performed,
            "violations": self.violations_detected,
            "status": "ACTIVE",
        }

    def active(self) -> bool:
        return self.get_status().get("status") == "ACTIVE"


def guard(engine: EnforcementEngine):

    def decorator(func: Callable):
        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                context = {"func_name": func.__name__, "args": args, "kwargs": kwargs}
                trace_id = None
                for arg in args:
                    if hasattr(arg, "trace_id") and arg.trace_id:
                        trace_id = arg.trace_id
                        break
                    if isinstance(arg, dict) and "trace_id" in arg:
                        trace_id = arg["trace_id"]
                        break
                if not trace_id and "trace_id" in kwargs:
                    trace_id = kwargs["trace_id"]
                if trace_id:
                    context["trace_id"] = trace_id
                await engine.validate_pre_execution(context)
                try:
                    res = await func(*args, **kwargs)
                    await engine.validate_post_execution(res)
                    return res
                except Exception as e:
                    engine.logger.log_event(
                        module="EnforcementEngine",
                        action="guard",
                        status="EXCEPTION",
                        message=f"{func.__name__}: {e}",
                        error=str(e),
                        level="ERROR",
                    )
                    raise e

            return async_wrapper
        else:

            def sync_wrapper(*args, **kwargs) -> NoReturn:
                raise RuntimeError(
                    "Synchronous execution not supported under EnforcementEngine. All guarded paths must be async."
                )

            return sync_wrapper

    return decorator


enforcement_engine = EnforcementEngine()
