"""Structured JSON logging for production. Configurable format (json | text) and context injection."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

__all__ = ["configure_logging", "get_logger", "CorrelationIDFilter", "logger", "StructuredLogger"]

# Standard LogRecord attributes to exclude from "extra"
_STANDARD_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "process", "processId", "message", "exc_info",
        "exc_text", "stack_info", "taskName", "correlation_id", "service",
    }
)


class JsonFormatter(logging.Formatter):
    """Format log records as a single-line JSON object for production ingestion."""

    def __init__(self, service_name: str = "qtrader") -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        from qtrader.core.config import Config
        ts = datetime.fromtimestamp(record.created, tz=Config.tz).isoformat()
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and v is not None
        }
        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "service": getattr(record, "service", self._service_name),
            "correlation_id": getattr(record, "correlation_id", "no-correlation"),
            "message": record.getMessage(),
        }
        if extra:
            payload["extra"] = extra
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    service_name: str = "qtrader",
) -> None:
    """Configure structured logging for the entire application.

    JSON format fields per log record:
    {
        "timestamp": "2026-03-15T01:25:19+00:00",
        "level": "INFO",
        "logger": "bot.runner",
        "service": "qtrader",
        "correlation_id": "...",
        "message": "...",
        "extra": {...}
    }

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        fmt: "json" for one-JSON-object-per-line; "text" for human-readable.
        service_name: Value for the "service" field in each record.

    Usage:
        configure_logging(level=settings.log_level)
        log = get_logger("bot", correlation_id="cycle-001")
        log.info("Signal generated", symbol="BTC/USDT", strength=0.85)
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if root.handlers:
        root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(root.level)
    if fmt == "json":
        handler.setFormatter(JsonFormatter(service_name=service_name))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
    root.addHandler(handler)
    # Inject correlation_id into records when filter is used
    root.addFilter(CorrelationIDFilter())


class _StructuredAdapter(logging.LoggerAdapter):
    """Adapter that merges context and log-call kwargs into the record's extra."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.get("extra") or {}
        # Move non-logging kwargs into extra so they appear in the JSON record
        reserved = {"extra", "exc_info", "stack_info", "stackLevel"}
        for k, v in list(kwargs.items()):
            if k not in reserved:
                extra[k] = v
                del kwargs[k]
        kwargs["extra"] = {**self.extra, **extra}
        return msg, kwargs


def get_logger(name: str, **context: Any) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that includes context fields in every log record.

    Args:
        name: Logger name (e.g. "qtrader.risk").
        **context: Keys (e.g. correlation_id, strategy) added to each record's "extra".

    Returns:
        LoggerAdapter that merges context into log calls. Pass keyword args in log
        calls to add them to the JSON "extra" field, e.g. log.info("msg", key=val).

    Example:
        log = get_logger("qtrader.risk", correlation_id="risk-001", strategy="momentum")
        log.warning("VaR limit breached", var_95=0.032, limit=0.020)
    """
    return _StructuredAdapter(logging.getLogger(name), context)


class CorrelationIDFilter(logging.Filter):
    """Logging filter that injects a correlation_id into all records.
    Set via: CorrelationIDFilter.set_id("cycle-001")
    Clear via: CorrelationIDFilter.clear_id()
    """

    _id: str | None = None

    @classmethod
    def set_id(cls, correlation_id: str) -> None:
        """Set the correlation ID for the current context (e.g. request or cycle)."""
        cls._id = correlation_id

    @classmethod
    def clear_id(cls) -> None:
        """Clear the correlation ID."""
        cls._id = None

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self._id or "no-correlation"
        if not hasattr(record, "service"):
            record.service = "qtrader"
        return True


# --- Doctest / pytest-style examples (run with pytest -v qtrader/core/logging.py) ---
def _example_configure_and_log() -> None:
    """Example: configure JSON logging and emit a structured record."""
    configure_logging(level="INFO", fmt="text", service_name="qtrader-test")
    log = get_logger("qtrader.test", correlation_id="ex-001")
    log.info("Example message", key="value")


def _example_correlation_filter() -> None:
    """Example: set correlation ID and clear it."""
    CorrelationIDFilter.set_id("cycle-002")
    assert CorrelationIDFilter._id == "cycle-002"
    CorrelationIDFilter.clear_id()
    assert CorrelationIDFilter._id is None


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
