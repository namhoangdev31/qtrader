from __future__ import annotations

from typing import Any, Optional


class BaseError(Exception):
    """
    Principal Error Class for QTrader.
    All system-specific exceptions must inherit from this class.
    
    Severity:
        1: Recoverable (Retry possible)
        2: Critical (Isolation required)
        3: Fatal (System Halt required)
    """
    severity: int = 1
    code: str = "ERR_BASE"

    def __init__(self, message: str, metadata: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.metadata = metadata or {}

    def __str__(self) -> str:
        return f"[{self.code}] Severity={self.severity} | {self.message}"


class RecoverableError(BaseError):
    """Exceptions that can be resolved via automated retry/backoff."""
    severity: int = 1
    code: str = "ERR_RECOVERABLE"


class ValidationError(BaseError):
    """Schema or input mismatches in data/config layers."""
    severity: int = 1
    code: str = "ERR_VALIDATION"


class CriticalError(BaseError):
    """State inconsistencies or execution mismatches requiring immediate intervention."""
    severity: int = 2
    code: str = "ERR_CRITICAL"


class FatalError(BaseError):
    """Terminal failures (state corruption, risk breach) requiring full system halt."""
    severity: int = 3
    code: str = "ERR_FATAL"


def classify_error(exc: Exception) -> BaseError:
    """
    Automated classification for unknown exceptions.
    Any exception not inheriting from BaseError is auto-escalated to FatalError.
    """
    if isinstance(exc, BaseError):
        return exc
    
    # Auto-escalation of unknown errors to prevent unmonitored risk exposure.
    return FatalError(
        message=f"Unknown Unhandled Exception: {type(exc).__name__}: {str(exc)}",
        metadata={"original_type": type(exc).__name__}
    )
