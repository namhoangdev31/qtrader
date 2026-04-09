from __future__ import annotations
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Generator


class LatencyViolation(Exception):
    pass


@dataclass(slots=True)
class StageMeasurement:
    stage: str
    duration_ms: float
    budget_ms: float
    breached: bool
    timestamp: float


@dataclass(slots=True)
class PipelineLatencyReport:
    stage_measurements: list[StageMeasurement] = field(default_factory=list)
    total_latency_ms: float = 0.0
    total_budget_ms: float = 100.0
    pipeline_breached: bool = False
    trace_id: str = ""
    timestamp: float = 0.0

    @property
    def sla_compliant(self) -> bool:
        return not self.pipeline_breached and (
            not any((m.breached for m in self.stage_measurements))
        )


class LatencyEnforcer:
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
        self._pipeline_start_ns = time.perf_counter_ns()
        self._stage_starts.clear()
        self._measurements.clear()
        self._total_latency_ns = 0
        logger.debug(f"[LATENCY] Pipeline started | Trace: {trace_id}")

    def end_pipeline(self, trace_id: str = "") -> PipelineLatencyReport:
        total_ms = self._total_latency_ns / 1000000.0
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
                f"[LATENCY] Pipeline BREACH | Total: {total_ms:.2f}ms > {total_budget:.1f}ms | Trace: {trace_id} | Violation #{self._violation_count}"
            )
            if self.fail_on_breach:
                raise LatencyViolation(
                    f"Pipeline latency {total_ms:.2f}ms exceeds budget {total_budget:.1f}ms"
                )
        return report

    @contextmanager
    def measure_stage(self, stage: str) -> Generator[None, None, None]:
        start_ns = time.perf_counter_ns()
        self._stage_starts[stage] = start_ns
        try:
            yield
        finally:
            end_ns = time.perf_counter_ns()
            duration_ns = end_ns - start_ns
            duration_ms = duration_ns / 1000000.0
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
            elif budget and duration_ms > budget * self.alert_threshold_pct:
                logger.info(
                    f"[LATENCY] Stage WARNING | {stage}: {duration_ms:.2f}ms ({duration_ms / budget:.0%} of budget {budget:.1f}ms)"
                )

    def get_status(self) -> dict[str, Any]:
        recent = self._reports[-10:] if self._reports else []
        avg_latency = sum((r.total_latency_ms for r in recent)) / len(recent) if recent else 0.0
        max_latency = max((r.total_latency_ms for r in recent), default=0.0)
        compliant_count = sum((1 for r in recent if r.sla_compliant))
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
        return {
            m.stage: {
                "duration_ms": m.duration_ms,
                "budget_ms": m.budget_ms,
                "breached": m.breached,
            }
            for m in self._measurements
        }

    def get_pipeline_data(self, trace_id: str) -> PipelineLatencyReport | None:
        for report in reversed(self._reports):
            if report.trace_id == trace_id:
                return report
        return None


latency_enforcer = LatencyEnforcer()
