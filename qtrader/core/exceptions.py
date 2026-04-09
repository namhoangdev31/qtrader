from typing import Any

from qtrader.core.errors import FatalError


class ConstraintViolation(Exception):
    def __init__(self, constraint_id: str, message: str) -> None:
        self.constraint_id = constraint_id
        self.message = message
        super().__init__(f"CONSTRAINT_VIOLATION | {constraint_id}: {message}")


class SystemHalt(FatalError):
    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message=f"SYSTEM_HALT | {message}", metadata=metadata)
