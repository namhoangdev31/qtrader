from __future__ import annotations

import contextvars
from types import TracebackType
from uuid import UUID, uuid4

from loguru import logger

_trace_context: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "trace_id", default=None
)


class TraceAuthority:
    @staticmethod
    def start_trace(trace_id: UUID | None = None) -> UUID:
        trace_id = trace_id or uuid4()
        _trace_context.set(trace_id)
        return trace_id

    @staticmethod
    def get_current_trace() -> UUID | None:
        return _trace_context.get()

    @staticmethod
    def ready() -> bool:
        return TraceAuthority.get_current_trace() is not None

    @staticmethod
    def clear_trace() -> None:
        _trace_context.set(None)

    @staticmethod
    def ensure_trace(trace_id: UUID | None = None) -> UUID:
        current = TraceAuthority.get_current_trace()
        if trace_id:
            if current and current != trace_id:
                logger.warning(
                    f"[TRACE] Overriding active trace_id {current} with explicit {trace_id}"
                )
            _trace_context.set(trace_id)
            return trace_id
        if current:
            return current
        new_trace = uuid4()
        logger.warning(f"[TRACE] Missing trace context. Injecting auto-generated: {new_trace}")
        _trace_context.set(new_trace)
        return new_trace

    @staticmethod
    def wrap_with_trace(trace_id: UUID):

        class TraceContextManager:
            def __init__(self, tid: UUID) -> None:
                self.tid = tid
                self.token: contextvars.Token | None = None

            def __enter__(self):
                self.token = _trace_context.set(self.tid)
                return self.tid

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                _trace_context.reset(self.token)

        return TraceContextManager(trace_id)

    @staticmethod
    def inject_trace(trace_id: UUID | str | None = None):
        if trace_id is None:
            trace_id = uuid4()
        elif isinstance(trace_id, str):
            try:
                trace_id = UUID(trace_id)
            except ValueError:
                trace_id = uuid4()
        return TraceAuthority.wrap_with_trace(trace_id)

    @staticmethod
    def generate() -> UUID:
        return uuid4()

    @staticmethod
    def propagate(source_event: Any) -> UUID:
        if hasattr(source_event, "trace_id"):
            tid = source_event.trace_id
            if isinstance(tid, str):
                tid = UUID(tid)
            TraceAuthority.start_trace(tid)
            return tid
        if hasattr(source_event, "metadata") and source_event.metadata:
            tid = source_event.metadata.get("trace_id")
            if tid:
                if isinstance(tid, str):
                    tid = UUID(tid)
                TraceAuthority.start_trace(tid)
                return tid
        return TraceAuthority.start_trace()
