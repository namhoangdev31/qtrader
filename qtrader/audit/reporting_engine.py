from __future__ import annotations
import logging
import time
from enum import Enum, auto
from typing import Any, Final
import polars as pl

_LOG = logging.getLogger("qtrader.audit.reporting_engine")


class ReportType(Enum):
    DAILY = auto()
    MONTHLY = auto()
    INCIDENT = auto()


class ComplianceReportingEngine:
    def __init__(self, reporting_id: str = "GENERIC_OVERSIGHT") -> None:
        self._id: Final[str] = reporting_id
        self._stats = {"total_reports_generated": 0}

    def generate_report(
        self,
        report_type: ReportType,
        trades: list[dict[str, Any]],
        violations: list[dict[str, Any]],
        risk_summary: dict[str, Any],
    ) -> dict[str, Any]:
        start_time = time.time()
        if trades:
            df_trades = pl.DataFrame(trades)
            pnl_sum = df_trades["pnl"].sum() if "pnl" in df_trades.columns else 0.0
        else:
            pnl_sum = 0.0
        violation_density = len(violations)
        report = {
            "status": "REPORT_GENERATED",
            "type": report_type.name,
            "reporting_id": self._id,
            "metrics": {
                "Platform_PnL": round(float(pnl_sum if pnl_sum is not None else 0.0), 4),
                "Violation_Count": violation_density,
                "Terminal_VaR": risk_summary.get("VaR", 0.0),
                "Terminal_MaxDD": risk_summary.get("MaxDD", 0.0),
            },
            "evidentiary_alerts": violations[:10],
            "timestamp": time.time(),
            "generation_latency_ms": round((time.time() - start_time) * 1000, 2),
        }
        self._stats["total_reports_generated"] += 1
        _LOG.info(
            f"[COMPLIANCE_REPORT] GENERATED | Type: {report_type.name} | PnL: {pnl_sum:.4f} | Violations: {violation_density}"
        )
        return report

    def get_reporting_stats(self) -> dict[str, Any]:
        return {"status": "AUDIT", "generation_count": self._stats["total_reports_generated"]}
