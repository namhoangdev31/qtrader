"""Structured JSON logging for production. Configurable format (json | text) and context injection."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

__all__ = ["configure_logging", "get_logger", "CorrelationIDFilter"]

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
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
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
        "logger": "qtrader.bot.runner",
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
        log = get_logger("qtrader.bot", correlation_id="cycle-001")
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
