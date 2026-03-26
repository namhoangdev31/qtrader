"""Consolidated loguru-based logging for production with trace_id support."""
from __future__ import annotations

import sys
from typing import Any

from loguru import logger

# Remove default handler
logger.remove()

# Add a standard stdout handler with JSON or colored text formatting
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | {extra}",
    level="INFO",
    enqueue=True,
)

def get_logger(name: str | None = None, trace_id: str | None = None) -> Any:
    """Return a logger bound with an optional trace_id."""
    log = logger
    if name:
        log = log.bind(module_name=name)
    if trace_id:
        log = log.bind(trace_id=trace_id)
    return log

# Default global logger
log = logger
