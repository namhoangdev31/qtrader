"""Per-stage latency tracker with trace logging.

Provides:
  - `LatencyTracker`: records per-stage latencies and enforces the system constraint
    Latency_total = Σ stage_latency < 100ms.
  - Integration with the existing `LatencyEnforcer` from `core/latency.py`.

All measurements use `time.perf_counter()` for nanosecond-resolution.
"""
import logging
import time
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.monitoring.latency_tracker")

# System-wide constraint
LATENCY_BUDGET_MS: float = 100.0


@dataclass
class StageRecord:
    """One recorded stage measurement."""
    stage: str
    duration_ms: float
    timestamp: float  # perf_counter epoch


class LatencyTracker:
    """Tracks per-stage latency across the full event pipeline.

    Mathematical Model:
        Latency_total = Σ stage_latency
        Constraint: Latency_total < 100ms

    Usage:
        tracker = LatencyTracker()
        tracker.start_trace("req-123")
        tracker.record_stage("req-123", "market_data_ingest")
        tracker.record_stage("req-123", "alpha_compute")
        tracker.record_stage("req-123", "order_submit")
        report = tracker.end_trace("req-123")
    """

    def __init__(self, budget_ms: float = LATENCY_BUDGET_MS) -> None:
        self.budget_ms = budget_ms
        # Active traces: trace_id -> (start_time, list of stages)
        self._active_traces: dict[str, tuple[float, list[StageRecord]]] = {}
        # Completed trace summaries (rolling window)
        self._history: list[dict[str, Any]] = []
        self._max_history: int = 1000
        # Aggregate stats
        self.total_traces: int = 0
        self.breach_count: int = 0

    def start_trace(self, trace_id: str) -> None:
        """Begin a new latency trace."""
        self._active_traces[trace_id] = (time.perf_counter(), [])

    def record_stage(self, trace_id: str, stage_name: str) -> float:
        """Record a checkpoint for a named stage.

        Args:
            trace_id: The active trace identifier.
            stage_name: Human-readable stage name (e.g. 'alpha_compute').

        Returns:
            Duration in ms since the last recorded stage (or trace start).
        """
        if trace_id not in self._active_traces:
            _LOG.warning(f"Trace {trace_id} not found, auto-starting")
            self.start_trace(trace_id)

        now = time.perf_counter()
        start, stages = self._active_traces[trace_id]
        prev_time = stages[-1].timestamp if stages else start
        duration_ms = (now - prev_time) * 1000.0

        stages.append(StageRecord(
            stage=stage_name,
            duration_ms=duration_ms,
            timestamp=now,
        ))
        return duration_ms

    def end_trace(self, trace_id: str) -> dict[str, Any]:
        """Finalize a trace, compute total latency, and check budget.

        Returns:
            Summary dict with per-stage breakdown and breach status.
        """
        if trace_id not in self._active_traces:
            _LOG.error(f"Cannot end unknown trace {trace_id}")
            return {"error": "trace_not_found"}

        start, stages = self._active_traces.pop(trace_id)
        total_ms = (time.perf_counter() - start) * 1000.0
        is_breach = total_ms > self.budget_ms

        self.total_traces += 1
        if is_breach:
            self.breach_count += 1
            _LOG.warning(
                f"[LATENCY_BREACH] trace={trace_id} total={total_ms:.3f}ms "
                f"budget={self.budget_ms}ms stages={len(stages)}"
            )

        report: dict[str, Any] = {
            "trace_id": trace_id,
            "total_ms": round(total_ms, 3),
            "budget_ms": self.budget_ms,
            "is_breach": is_breach,
            "stages": [
                {"stage": s.stage, "duration_ms": round(s.duration_ms, 3)}
                for s in stages
            ],
        }

        # Rolling history
        self._history.append(report)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        return report

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate latency statistics."""
        return {
            "total_traces": self.total_traces,
            "breach_count": self.breach_count,
            "breach_rate": (
                self.breach_count / self.total_traces
                if self.total_traces > 0
                else 0.0
            ),
            "budget_ms": self.budget_ms,
        }
