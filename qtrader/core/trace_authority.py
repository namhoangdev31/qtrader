from __future__ import annotations

import contextvars
from uuid import UUID, uuid4

from loguru import logger

# Context Variable to store the active trace_id across async contexts.
_trace_context: contextvars.ContextVar[UUID | None] = contextvars.ContextVar("trace_id", default=None)


class TraceAuthority:
    """
    Central authority for trace ID generation and implicit propagation.
    Ensures that every event created within a transaction context inherits the same trace_id.
    """

    @staticmethod
    def start_trace(trace_id: UUID | None = None) -> UUID:
        """
        Generate a new trace_id or set an existing one in the current context.
        """
        trace_id = trace_id or uuid4()
        _trace_context.set(trace_id)
        return trace_id

    @staticmethod
    def get_current_trace() -> UUID | None:
        """
        Retrieve the trace_id from the current context.
        Returns None if no trace is active.
        """
        return _trace_context.get()

    @staticmethod
    def ready() -> bool:
        """Checks if the trace authority is functioning and context is ready."""
        return TraceAuthority.get_current_trace() is not None

    @staticmethod
    def clear_trace() -> None:
        """Clear the current trace context."""
        _trace_context.set(None)

    @staticmethod
    def ensure_trace(trace_id: UUID | None = None) -> UUID:
        """
        Retrieve existing trace_id or generate/inject a new one if missing.
        """
        current = TraceAuthority.get_current_trace()
        if trace_id:
            # If a trace_id is explicitly provided, it overrides or sets the context.
            if current and current != trace_id:
                logger.warning(
                    f"[TRACE] Overriding active trace_id {current} with explicit {trace_id}"
                )
            _trace_context.set(trace_id)
            return trace_id
            
        if current:
            return current
            
        # No trace active - generate and log warning for audit trail.
        new_trace = uuid4()
        logger.warning(f"[TRACE] Missing trace context. Injecting auto-generated: {new_trace}")
        _trace_context.set(new_trace)
        return new_trace

    @staticmethod
    def wrap_with_trace(trace_id: UUID):
        """
        Decorator/Context manager helper to wrap a block of execution with a specific trace.
        """
        class TraceContextManager:
            def __init__(self, tid: UUID):
                self.tid = tid
                self.token: contextvars.Token | None = None

            def __enter__(self):
                self.token = _trace_context.set(self.tid)
                return self.tid

            def __exit__(self, exc_type, exc_val, exc_tb):
                _trace_context.reset(self.token)

        return TraceContextManager(trace_id)

    @staticmethod
    def generate() -> UUID:
        """Alias for uuid4() to maintain API compatibility."""
        return uuid4()

    @staticmethod
    def propagate(source_event: Any) -> UUID:
        """
        Extract trace ID from a source event for propagation to the context.
        """
        if hasattr(source_event, 'trace_id'):
            tid = source_event.trace_id
            if isinstance(tid, str):
                tid = UUID(tid)
            TraceAuthority.start_trace(tid)
            return tid
        
        # Fallback to metadata
        if hasattr(source_event, 'metadata') and source_event.metadata:
            tid = source_event.metadata.get('trace_id')
            if tid:
                if isinstance(tid, str):
                    tid = UUID(tid)
                TraceAuthority.start_trace(tid)
                return tid
                
        return TraceAuthority.start_trace()
