"""Tests for [LATENCY_TRACE_SYSTEM]: latency tracking + trace logs."""
import time

import pytest

from qtrader.monitoring.latency_tracker import LatencyTracker
from qtrader.monitoring.trace_manager import (
    TraceManager,
    generate_trace_id,
    get_current_trace_id,
    set_current_trace_id,
)


class TestLatencyTracker:
    """Validate per-stage latency tracking and budget enforcement."""

    def test_basic_trace_lifecycle(self) -> None:
        tracker = LatencyTracker(budget_ms=100.0)
        tracker.start_trace("t1")
        tracker.record_stage("t1", "stage_a")
        tracker.record_stage("t1", "stage_b")
        report = tracker.end_trace("t1")

        assert report["trace_id"] == "t1"
        assert report["total_ms"] >= 0
        assert len(report["stages"]) == 2
        assert report["stages"][0]["stage"] == "stage_a"
        assert report["stages"][1]["stage"] == "stage_b"

    def test_budget_breach_detected(self) -> None:
        # Use a very small budget so any real work breaches it
        tracker = LatencyTracker(budget_ms=0.001)
        tracker.start_trace("t2")
        # Do some minimal work to ensure non-zero time
        _ = sum(range(100))
        tracker.record_stage("t2", "compute")
        report = tracker.end_trace("t2")

        assert report["is_breach"] is True
        assert tracker.breach_count == 1

    def test_no_breach_within_budget(self) -> None:
        tracker = LatencyTracker(budget_ms=5000.0)  # Very generous
        tracker.start_trace("t3")
        tracker.record_stage("t3", "fast_stage")
        report = tracker.end_trace("t3")

        assert report["is_breach"] is False

    def test_stats_aggregation(self) -> None:
        tracker = LatencyTracker(budget_ms=5000.0)
        for i in range(5):
            tid = f"trace_{i}"
            tracker.start_trace(tid)
            tracker.record_stage(tid, "work")
            tracker.end_trace(tid)

        stats = tracker.get_stats()
        assert stats["total_traces"] == 5
        assert stats["breach_count"] == 0
        assert stats["breach_rate"] == 0.0


class TestTraceManager:
    """Validate distributed trace management."""

    def test_begin_and_end_trace(self) -> None:
        tm = TraceManager()
        trace_id = tm.begin_trace("market_data", symbol="BTC/USD")

        tm.add_span(trace_id, "alpha_compute", duration_ms=0.5)
        tm.add_span(trace_id, "order_submit", duration_ms=1.2)

        result = tm.end_trace(trace_id)
        assert result is not None
        assert result["origin"] == "market_data"
        assert len(result["spans"]) == 2
        assert result["total_ms"] == 1.7

    def test_trace_id_context_propagation(self) -> None:
        tm = TraceManager()
        trace_id = tm.begin_trace("test_origin")

        # The trace manager sets the ContextVar
        assert get_current_trace_id() == trace_id

    def test_recent_traces(self) -> None:
        tm = TraceManager()
        for i in range(3):
            tid = tm.begin_trace(f"origin_{i}")
            tm.add_span(tid, "work", duration_ms=float(i))
            tm.end_trace(tid)

        recent = tm.get_recent_traces(limit=2)
        assert len(recent) == 2

    def test_generate_trace_id_unique(self) -> None:
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) == 100  # All unique
