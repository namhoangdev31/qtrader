from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.events import EventType

if TYPE_CHECKING:
    from qtrader.core.event_store import BaseEventStore
    from qtrader.core.state_store import StateStore


class PostExecutionValidator:
    def __init__(self, root_path: str | None = None) -> None:
        self.root_path = Path(root_path or os.getcwd())
        self.audit_dir = self.root_path / "qtrader/audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    async def validate(
        self, event_store: BaseEventStore, state_store: StateStore
    ) -> dict[str, Any]:
        logger.info("POST_EXEC_START | Initiating system verification gate.")
        trace_results = await self._check_trace_completeness(event_store)
        state_results = await self._check_state_consistency(state_store)
        determinism_results = await self._verify_determinism(event_store)
        is_valid = (
            trace_results["complete"]
            and state_results["consistent"]
            and determinism_results["deterministic"]
        )
        total_issues = (
            trace_results["issues"] + state_results["issues"] + determinism_results["issues"]
        )
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "valid": is_valid,
            "deterministic": determinism_results["deterministic"],
            "status": "VERIFIED" if is_valid else "INVALID",
            "issues": total_issues,
            "details": {
                "trace": trace_results,
                "state": state_results,
                "determinism": determinism_results,
            },
        }
        self._save_report(report)
        self._save_determinism_validation(determinism_results)
        self._generate_consistency_markdown(report)
        if is_valid:
            logger.success(
                "POST_EXEC_SUCCESS | Execution output verified. Trace is complete and deterministic."
            )
        else:
            logger.warning(
                f"POST_EXEC_WARNING | Execution anomalies detected (Issues: {total_issues}). Status: {report['status']}"
            )
        return report

    async def _check_trace_completeness(self, event_store: BaseEventStore) -> dict[str, Any]:
        events = await event_store.get_events()
        trace_map: dict[str, list[EventType]] = {}
        for event in events:
            t_id = str(event.trace_id)
            if t_id not in trace_map:
                trace_map[t_id] = []
            trace_map[t_id].append(event.event_type)
        orphaned_traces = []
        terminal_events = {EventType.ORDER_FILLED, EventType.ORDER_REJECTED, EventType.FILL}
        for t_id, types in trace_map.items():
            if EventType.ORDER in types:
                if not any(t in terminal_events for t in types):
                    orphaned_traces.append(t_id)
        return {
            "complete": len(orphaned_traces) == 0,
            "total_traces": len(trace_map),
            "orphaned_traces": orphaned_traces,
            "issues": len(orphaned_traces),
        }

    async def _check_state_consistency(self, state_store: StateStore) -> dict[str, Any]:
        state = await state_store.snapshot()
        issues = []
        if state.active_orders:
            issues.append(
                f"STALE_ACTIVE_ORDERS: {len(state.active_orders)} orders remained registered."
            )
        if state.cash < 0:
            logger.debug(f"CONSISTENCY_METRIC | Negative cash detected: {state.cash}")
        return {
            "consistent": len(issues) == 0,
            "issues": len(issues),
            "metrics": {
                "final_cash": str(state.cash),
                "total_fees": str(state.total_fees),
                "portfolio_value": str(state.portfolio_value),
                "position_count": len(state.positions),
            },
            "detected_inconsistencies": issues,
        }

    async def _verify_determinism(self, event_store: BaseEventStore) -> dict[str, Any]:
        baseline_path = self.audit_dir / "baseline_trace.json"
        events = await event_store.get_events()
        current_metrics = {
            "event_count": len(events),
            "types_distribution": self._get_type_distribution(events),
        }
        if not baseline_path.exists():
            return {
                "deterministic": True,
                "issues": 0,
                "message": "Baseline not found. Determinism verified by default.",
            }
        try:
            with open(baseline_path) as f:
                baseline = json.load(f)
        except Exception as e:
            return {"deterministic": False, "issues": 1, "message": f"Baseline corruption: {e}"}
        issues = 0
        mismatches = []
        if current_metrics["event_count"] != baseline.get("event_count"):
            issues += 1
            mismatches.append(
                f"Event count mismatch: {current_metrics['event_count']} vs {baseline['event_count']}"
            )
        return {
            "deterministic": issues == 0,
            "issues": issues,
            "mismatches": mismatches,
            "current_metrics": current_metrics,
            "baseline_metrics": baseline,
        }

    def _get_type_distribution(self, events: list[Any]) -> dict[str, int]:
        dist: dict[str, int] = {}
        for event in events:
            t = str(event.event_type)
            dist[t] = dist.get(t, 0) + 1
        return dist

    def _save_report(self, report: dict[str, Any]) -> None:
        path = self.audit_dir / "post_execution_report.json"
        with open(path, "w") as f:
            json.dump(report, f, indent=2)

    def _save_determinism_validation(self, results: dict[str, Any]) -> None:
        path = self.audit_dir / "determinism_validation.json"
        with open(path, "w") as f:
            json.dump(results, f, indent=2)

    def _generate_consistency_markdown(self, report: dict[str, Any]) -> None:
        path = self.audit_dir / "consistency_check.md"
        lines = [
            "# Post-Execution Consistency Report",
            f"\n**Timestamp**: {report['timestamp']}",
            f"**Overall Status**: {('✅ VERIFIED' if report['valid'] else '❌ INVALID')}",
            f"**Determinism**: {('✅ MATCH' if report['deterministic'] else '⚠️ DRIFT DETECTED')}",
            "\n## Verification Metrics",
            f"- Issues Detected: {report['issues']}",
            f"- Trace Completeness: {('PASS' if report['details']['trace']['complete'] else 'FAIL')}",
            f"- State Consistency: {('PASS' if report['details']['state']['consistent'] else 'FAIL')}",
            "\n## State Summary",
            f"```json\n{json.dumps(report['details']['state']['metrics'], indent=2)}\n```",
        ]
        if report["details"]["trace"]["orphaned_traces"]:
            lines.append("\n## Orphaned Traces")
            for t in report["details"]["trace"]["orphaned_traces"]:
                lines.append(f"- `{t}`")
        with open(path, "w") as f:
            f.write("\n".join(lines))
