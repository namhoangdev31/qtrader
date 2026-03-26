"""Distributed trace manager for end-to-end request tracing.

Provides unique trace IDs for correlating events across:
  MarketData → Alpha → Signal → Order → Fill

Each trace carries a UUID and propagates through the EventBus,
enabling full observability of the event pipeline.
"""
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any

_LOG = logging.getLogger("qtrader.monitoring.trace_manager")

# Async-safe context variable for trace propagation
_current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="no-trace")


def generate_trace_id() -> str:
    """Generate a new unique trace ID."""
    return str(uuid.uuid4())


def get_current_trace_id() -> str:
    """Get the trace ID from the current async context."""
    return _current_trace_id.get()


def set_current_trace_id(trace_id: str) -> None:
    """Set the trace ID for the current async context."""
    _current_trace_id.set(trace_id)


class TraceManager:
    """Manages distributed traces across the event pipeline.

    Usage:
        tm = TraceManager()
        trace_id = tm.begin_trace("market_data_ingest", symbol="BTC/USD")
        tm.add_span(trace_id, "alpha_compute", duration_ms=0.5)
        tm.add_span(trace_id, "order_submit", duration_ms=1.2)
        tm.end_trace(trace_id)
    """

    def __init__(self) -> None:
        self._traces: dict[str, dict[str, Any]] = {}
        self._completed: list[dict[str, Any]] = []
        self._max_completed: int = 5000

    def begin_trace(self, origin: str, **metadata: Any) -> str:
        """Start a new trace from a given origin point.

        Args:
            origin: The component that initiated the trace.
            **metadata: Arbitrary key-value pairs to attach.

        Returns:
            The generated trace_id.
        """
        trace_id = generate_trace_id()
        self._traces[trace_id] = {
            "trace_id": trace_id,
            "origin": origin,
            "start_ts": datetime.utcnow().isoformat(),
            "spans": [],
            "metadata": metadata,
        }
        set_current_trace_id(trace_id)
        return trace_id

    def add_span(
        self,
        trace_id: str,
        span_name: str,
        duration_ms: float = 0.0,
        **metadata: Any,
    ) -> None:
        """Record a named span within an active trace.

        Args:
            trace_id: The trace to add the span to.
            span_name: Human-readable identifier for the span.
            duration_ms: Duration of this span in milliseconds.
            **metadata: Additional context for debugging.
        """
        if trace_id not in self._traces:
            _LOG.warning(f"Trace {trace_id} not found, span '{span_name}' dropped")
            return

        self._traces[trace_id]["spans"].append({
            "span": span_name,
            "duration_ms": round(duration_ms, 3),
            "ts": datetime.utcnow().isoformat(),
            **metadata,
        })

    def end_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Finalize a trace and move it to the completed buffer.

        Returns:
            The completed trace record, or None if not found.
        """
        trace = self._traces.pop(trace_id, None)
        if trace is None:
            _LOG.warning(f"Cannot end unknown trace {trace_id}")
            return None

        trace["end_ts"] = datetime.utcnow().isoformat()
        total_ms = sum(s["duration_ms"] for s in trace["spans"])
        trace["total_ms"] = round(total_ms, 3)

        self._completed.append(trace)
        if len(self._completed) > self._max_completed:
            self._completed.pop(0)

        _LOG.debug(
            f"Trace completed: id={trace_id} origin={trace['origin']} "
            f"spans={len(trace['spans'])} total_ms={trace['total_ms']}"
        )
        return trace

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Retrieve an active or completed trace by ID."""
        if trace_id in self._traces:
            return self._traces[trace_id]
        for t in reversed(self._completed):
            if t["trace_id"] == trace_id:
                return t
        return None

    def get_recent_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent completed traces."""
        return self._completed[-limit:]
