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
    def __init__(self, log_dir: str | None = None) -> None:
        self._setup_logger(log_dir)

    def _setup_logger(self, log_dir: str | None) -> None:
        logger.remove()
        logger.add(
            sys.stdout, format="{message}", serialize=False, level=os.getenv("LOG_LEVEL", "INFO")
        )
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


qlogger = QTraderLogger(log_dir="logs")
log_event = qlogger.log_event
log = logger
