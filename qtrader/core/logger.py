from __future__ import annotations

import datetime
import json
import os
import sys
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.trace_authority import TraceAuthority

if TYPE_CHECKING:
    from collections.abc import Mapping


class QTraderLogger:
    """
    Structured Logging Authority for qtrader.
    Standardizes on JSON output to ensure 100% queryable and audit-compliant traces.
    Automatically injects trace_id from execution context.
    """

    def __init__(self, log_dir: str | None = None) -> None:
        self._setup_logger(log_dir)

    def _setup_logger(self, log_dir: str | None) -> None:
        """Configures loguru to use a custom structured JSON sink."""
        # 1. Remove default sink
        logger.remove()

        # 2. Add structured JSON sink (Standard Out)
        logger.add(
            sys.stdout,
            format="{message}",
            serialize=False,  # We'll do custom serialization in log_event
            level=os.getenv("LOG_LEVEL", "INFO"),
        )

        # 3. Add file sink if log_dir provided
        if log_dir:
            log_path = os.path.join(log_dir, "qtrader.json")
            logger.add(
                log_path,
                rotation="100 MB",
                retention="14 days",
                format="{message}",
                serialize=False,
                level="INFO",
                encoding="utf-8",
            )

    def log_event(
        self,
        module: str,
        action: str,
        status: str = "SUCCESS",
        message: str | None = None,
        latency_ms: float | None = None,
        metadata: Mapping[str, Any] | None = None,
        error: str | None = None,
        level: str = "INFO",
    ) -> None:
        """
        Produce a structured JSON log entry compliant with logging_schema.json.
        Standardizes on ISO 8601 timestamps and trace_id injection.
        """
        # Automatically pull trace_id from context
        current_trace = TraceAuthority.get_current_trace()
        trace_id = str(current_trace) if current_trace else "NO_TRACE"

        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "trace_id": trace_id,
            "module": module,
            "action": action,
            "status": status,
            "level": level,
            "message": message or f"{module}:{action}",
            "latency_ms": latency_ms,
            "metadata": metadata or {},
            "error": error,
        }

        # Use loguru to handle serialization and output to all sinks
        # We manually stringify to ensure we match the exact schema
        json_msg = json.dumps(log_entry)

        if level == "INFO":
            logger.info(json_msg)
        elif level == "ERROR" or status == "FAILURE":
            logger.error(json_msg)
        elif level == "WARNING":
            logger.warning(json_msg)
        elif level == "SUCCESS":
            logger.success(json_msg)
        elif level == "CRITICAL":
            logger.critical(json_msg)
        else:
            logger.debug(json_msg)


# Single source of logging truth
qlogger = QTraderLogger(log_dir="logs")
log_event = qlogger.log_event
log = logger  # Backward compatibility alias
