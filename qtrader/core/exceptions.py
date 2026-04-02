from typing import Any

from qtrader.core.errors import FatalError


class ConstraintViolation(Exception):
    """Raised when a system runtime constraint is violated."""
    def __init__(self, constraint_id: str, message: str):
        self.constraint_id = constraint_id
        self.message = message
        super().__init__(f"CONSTRAINT_VIOLATION | {constraint_id}: {message}")

class SystemHalt(FatalError):
    """Raised when the RuntimeGatekeeper decides to halt the system due to critical violations."""
    def __init__(self, message: str, metadata: dict[str, Any] | None = None):
        super().__init__(message=f"SYSTEM_HALT | {message}", metadata=metadata)
