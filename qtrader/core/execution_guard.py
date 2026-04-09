import functools
import json
import os
from collections.abc import Callable
from typing import Any, Optional, TypeVar

from loguru import logger

from qtrader.core.system_state import SystemState, state_manager

F = TypeVar("F", bound=Callable[..., Any])


class ExecutionGateRegistry:
    """Audit Layer for Sovereign Execution Attempt Tracking."""

    _instance: Optional["ExecutionGateRegistry"] = None
    _blocked_attempts: int = 0
    _report_path: str = "qtrader/audit/guard_report.json"

    def __new__(cls) -> "ExecutionGateRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def log_blocked(self, module: str, function: str) -> None:
        """Track and log an unauthorized execution attempt."""
        self._blocked_attempts += 1
        logger.critical(
            f"EXECUTION_GUARD_VIOLATION | Blocked attempt: {module}.{function} | SystemState: {state_manager.state.name}"
        )
        self.generate_report()

    def generate_report(self) -> None:
        """Produce the global guard status report."""
        report = {
            "blocked_attempts": self._blocked_attempts,
            "status": "GUARD_ACTIVE",
            "system_state": state_manager.state.name,
        }

        # Ensure audit directory exists
        os.makedirs(os.path.dirname(self._report_path), exist_ok=True)

        with open(self._report_path, "w") as f:
            json.dump(report, f, indent=2)


# Global Registry
gate_registry = ExecutionGateRegistry()


def require_initialized(func: F) -> F:
    """Decorator to enforce that a function is called only in INITIALIZED/RUNNING state."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        current_state = state_manager.state
        if current_state not in [SystemState.READY, SystemState.RUNNING]:
            gate_registry.log_blocked(func.__module__, func.__name__)
            raise RuntimeError(
                f"Illegal execution attempt: {func.__name__} requires INITIALIZED system state (Current: {current_state.name})"
            )
        return func(*args, **kwargs)

    # Check for async functions
    if hasattr(func, "__await__") or (hasattr(func, "__code__") and func.__code__.co_flags & 0x80):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_state = state_manager.state
            if current_state not in [SystemState.READY, SystemState.RUNNING]:
                gate_registry.log_blocked(func.__module__, func.__name__)
                raise RuntimeError(
                    f"Illegal execution attempt: {func.__name__} requires INITIALIZED system state (Current: {current_state.name})"
                )
            return await func(*args, **kwargs)

        return async_wrapper  # type: ignore

    return wrapper  # type: ignore
