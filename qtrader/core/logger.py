import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict

import uuid


class StructuredLogger:
    """Structured JSON logger with correlation_id support."""

    def __init__(self, name: str = "qtrader", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        # Remove existing handlers to avoid duplicate logs
        self.logger.handlers.clear()
        # Add stdout handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)

    class JSONFormatter(logging.Formatter):
        """JSON log formatter."""

        def format(self, record: logging.LogRecord) -> str:
            log_entry: Dict[str, Any] = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            # Add extra fields from the record
            if hasattr(record, "correlation_id"):
                log_entry["correlation_id"] = record.correlation_id
            # Add any other extra fields
            for key, value in record.__dict__.items():
                if key not in ["args", "asctime", "created", "exc_info", "exc_text", "filename",
                               "funcName", "id", "levelname", "levelno", "lineno", "module",
                               "msecs", "message", "msg", "name", "pathname", "process",
                               "processName", "relativeCreated", "stack_info", "thread", "threadName"]:
                    log_entry[key] = value
            return json.dumps(log_entry, default=str)

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal log method to inject correlation_id if not provided."""
        if "correlation_id" not in kwargs:
            kwargs["correlation_id"] = str(uuid.uuid4())
        self.logger.log(level, message, extra=kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, **kwargs)


# Default logger instance
logger = StructuredLogger()
