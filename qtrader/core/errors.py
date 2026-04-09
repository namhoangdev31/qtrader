from __future__ import annotations

from typing import Any


class BaseError(Exception):
    severity: int = 1
    code: str = "ERR_BASE"

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.metadata = metadata or {}

    def __str__(self) -> str:
        return f"[{self.code}] Severity={self.severity} | {self.message}"


class RecoverableError(BaseError):
    severity: int = 1
    code: str = "ERR_RECOVERABLE"


class ValidationError(BaseError):
    severity: int = 1
    code: str = "ERR_VALIDATION"


class CriticalError(BaseError):
    severity: int = 2
    code: str = "ERR_CRITICAL"


class FatalError(BaseError):
    severity: int = 3
    code: str = "ERR_FATAL"


def classify_error(exc: Exception) -> BaseError:
    if isinstance(exc, BaseError):
        return exc
    return FatalError(
        message=f"Unknown Unhandled Exception: {type(exc).__name__}: {exc!s}",
        metadata={"original_type": type(exc).__name__},
    )
