"""Latency Enforcement — Standash §5.1.

Active pipeline instrumentation with per-stage latency budgets.
Enforces the institutional 100ms end-to-end SLA.

Stages:
- Market → Alpha: < 5ms
- Alpha → Signal: < 5ms
- Signal → Order: < 10ms
- Order → Fill: < 50ms
- TOTAL: < 100ms
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Generator


class LatencyViolation(Exception):
    """Exception raised when an execution stage exceeds its defined latency budget."""

    pass


@dataclass(slots=True)
class StageMeasurement:
    """Single stage latency measurement."""

    stage: str
    duration_ms: float
    budget_ms: float
    breached: bool
    timestamp: float


@dataclass(slots=True)
class PipelineLatencyReport:
    """Full pipeline latency report for a single event lifecycle."""

    stage_measurements: list[StageMeasurement] = field(default_factory=list)
    total_latency_ms: float = 0.0
    total_budget_ms: float = 100.0
    pipeline_breached: bool = False
    trace_id: str = ""
    timestamp: float = 0.0

    @property
    def sla_compliant(self) -> bool:
        return not self.pipeline_breached and not any(m.breached for m in self.stage_measurements)


class LatencyEnforcer:
    """Active Latency Enforcer — Standash §5.1.

    Instruments the critical path and enforces latency budgets at each stage.
    Provides:
    - Per-stage budget enforcement
    - End-to-end pipeline budget enforcement
    - Automatic violation logging and alerting
    - Context manager for clean instrumentation
    """

    DEFAULT_BUDGETS: dict[str, float] = {
        "market_data_ingestion": 5.0,
        "alpha_computation": 5.0,
        "signal_generation": 5.0,
        "portfolio_allocation": 10.0,
        "risk_check": 5.0,
        "order_routing": 10.0,
        "order_submission": 10.0,
        "fill_processing": 50.0,
        "total_end_to_end": 100.0,
    }

    def __init__(
        self,
        budgets: dict[str, float] | None = None,
        fail_on_breach: bool = True,
        alert_threshold_pct: float = 0.8,
    ) -> None:
        self.budgets = budgets or dict(self.DEFAULT_BUDGETS)
        self.fail_on_breach = fail_on_breach
        self.alert_threshold_pct = alert_threshold_pct
        self._stage_starts: dict[str, float] = {}
        self._measurements: list[StageMeasurement] = []
        self._total_latency_ns: int = 0
        self._pipeline_start_ns: int = 0
        self._violation_count: int = 0
        self._reports: list[PipelineLatencyReport] = []

    def start_pipeline(self, trace_id: str = "") -> None:
        """Start a new pipeline measurement cycle."""
        self._pipeline_start_ns = time.perf_counter_ns()
        self._stage_starts.clear()
        self._measurements.clear()
        self._total_latency_ns = 0
        logger.debug(f"[LATENCY] Pipeline started | Trace: {trace_id}")

    def end_pipeline(self, trace_id: str = "") -> PipelineLatencyReport:
        """End pipeline measurement and generate report."""
        total_ms = self._total_latency_ns / 1_000_000.0
        total_budget = self.budgets.get("total_end_to_end", 100.0)
        breached = total_ms > total_budget

        report = PipelineLatencyReport(
            stage_measurements=list(self._measurements),
            total_latency_ms=total_ms,
            total_budget_ms=total_budget,
            pipeline_breached=breached,
            trace_id=trace_id,
            timestamp=time.time(),
        )
        self._reports.append(report)
        if len(self._reports) > 1000:
            self._reports = self._reports[-500:]

        if breached:
            self._violation_count += 1
            logger.error(
                f"[LATENCY] Pipeline BREACH | Total: {total_ms:.2f}ms > {total_budget:.1f}ms | "
                f"Trace: {trace_id} | Violation #{self._violation_count}"
            )
            if self.fail_on_breach:
                raise LatencyViolation(
                    f"Pipeline latency {total_ms:.2f}ms exceeds budget {total_budget:.1f}ms"
                )

        return report

    @contextmanager
    def measure_stage(self, stage: str) -> Generator[None, None, None]:
        """Context manager for measuring a single stage.

        Usage:
            with enforcer.measure_stage("alpha_computation"):
                result = compute_alpha(data)
        """
        start_ns = time.perf_counter_ns()
        self._stage_starts[stage] = start_ns
        try:
            yield
        finally:
            end_ns = time.perf_counter_ns()
            duration_ns = end_ns - start_ns
            duration_ms = duration_ns / 1_000_000.0
            self._total_latency_ns += duration_ns

            budget = self.budgets.get(stage)
            breached = budget is not None and duration_ms > budget

            measurement = StageMeasurement(
                stage=stage,
                duration_ms=duration_ms,
                budget_ms=budget or 0.0,
                breached=breached,
                timestamp=time.time(),
            )
            self._measurements.append(measurement)

            if breached:
                self._violation_count += 1
                logger.warning(
                    f"[LATENCY] Stage BREACH | {stage}: {duration_ms:.2f}ms > {budget:.1f}ms"
                )
                if self.fail_on_breach:
                    raise LatencyViolation(
                        f"Stage '{stage}' latency {duration_ms:.2f}ms exceeds budget {budget:.1f}ms"
                    )
            elif budget and duration_ms > (budget * self.alert_threshold_pct):
                logger.info(
                    f"[LATENCY] Stage WARNING | {stage}: {duration_ms:.2f}ms "
                    f"({duration_ms / budget:.0%} of budget {budget:.1f}ms)"
                )

    def get_status(self) -> dict[str, Any]:
        """Return latency enforcer status."""
        recent = self._reports[-10:] if self._reports else []
        avg_latency = sum(r.total_latency_ms for r in recent) / len(recent) if recent else 0.0
        max_latency = max((r.total_latency_ms for r in recent), default=0.0)
        compliant_count = sum(1 for r in recent if r.sla_compliant)

        return {
            "budgets": self.budgets,
            "fail_on_breach": self.fail_on_breach,
            "violation_count": self._violation_count,
            "total_reports": len(self._reports),
            "recent_avg_latency_ms": round(avg_latency, 2),
            "recent_max_latency_ms": round(max_latency, 2),
            "recent_sla_compliance_pct": round(compliant_count / len(recent) * 100, 1)
            if recent
            else 100.0,
        }

    def get_current_measurements(self) -> dict[str, dict[str, float]]:
        """Return the most recent stage measurements."""
        return {
            m.stage: {
                "duration_ms": m.duration_ms,
                "budget_ms": m.budget_ms,
                "breached": m.breached
            } for m in self._measurements
        }

    def get_pipeline_data(self, trace_id: str) -> PipelineLatencyReport | None:
        """Retrieve the most recent report for a specific trace ID."""
        for report in reversed(self._reports):
            if report.trace_id == trace_id:
                return report
        return None


# Global singleton
latency_enforcer = LatencyEnforcer()
