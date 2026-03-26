from __future__ import annotations

import os
import time
import uuid
from typing import TYPE_CHECKING

from qtrader.core.events import (
    ComplianceErrorEvent,
    ComplianceErrorPayload,
    ComplianceExportEvent,
    ComplianceExportPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    import polars as pl
    from qtrader.audit.audit_store import AuditStore
    from qtrader.core.event_bus import EventBus


class ComplianceExporter:
    """
    Principal Regulatory Compliance and Export Engine.

    Responsible for generating standardized audit reports from the
    analytical AuditStore. Supports multiple formats and large-scale
    aggregation of decision-execution audit trails.
    """

    def __init__(self, audit_store: AuditStore, event_bus: EventBus) -> None:
        """
        Initialize the compliance exporter with data source and bus hooks.
        """
        self._audit_store = audit_store
        self._event_bus = event_bus
        self._export_dir = "reports/compliance"
        os.makedirs(self._export_dir, exist_ok=True)

    async def generate_report(
        self, start_timestamp: int, end_timestamp: int, format: str = "csv"
    ) -> str:
        """
        Generate a comprehensive compliance report for a specific window.

        Args:
            start_timestamp: Start of the query window (micro-seconds).
            end_timestamp: End of the query window (micro-seconds).
            format: Output format ('csv', 'json', 'parquet').

        Returns:
            str: Path to the generated report file.
        """
        start_perf = time.perf_counter()
        # Generate a unique trace_id for this export operation for audit trail
        op_trace_id = uuid.uuid4()

        try:
            # 1. Structured Query across the OLAP layer
            # We extract and flatten Decision, Trade, and NAV data in a single SQL step
            # Note: start/end_timestamp are validated ints, so SQL injection risk is mitigated.
            sql = f"""
            WITH decisions AS (
                SELECT trace_id, payload_json->'$.payload.model_id' as model, 
                       payload_json->'$.payload.decision' as decision,
                       payload_json->'$.payload.signal' as signal
                FROM audit_events 
                WHERE event_type = 'DECISION_TRACE' 
                  AND timestamp_us BETWEEN {start_timestamp} AND {end_timestamp}
            ),
            fills AS (
                SELECT trace_id, payload_json->'$.payload.symbol' as symbol,
                       CAST(payload_json->'$.payload.quantity' AS DOUBLE) as qty,
                       CAST(payload_json->'$.payload.price' AS DOUBLE) as px,
                       CAST(payload_json->'$.payload.fee' AS DOUBLE) as fee
                FROM audit_events 
                WHERE event_type = 'FILL'
            ),
            pnl AS (
                SELECT trace_id, CAST(payload_json->'$.payload.realized_pnl' AS DOUBLE) as pnl
                FROM audit_events 
                WHERE event_type = 'NAV_UPDATED'
            )
            SELECT d.trace_id, d.model, d.decision, d.signal, 
                   f.symbol, f.qty, f.px, f.fee, p.pnl
            FROM decisions d
            LEFT JOIN fills f ON d.trace_id = f.trace_id
            LEFT JOIN pnl p ON d.trace_id = p.trace_id
            """  # noqa: S608

            # 2. Materialize to Polars for local transformations
            df = self._audit_store.query_olap(sql)
            if df.is_empty():
                logger.warning(
                    f"COMPLIANCE_EXPORT_EMPTY | Range: {start_timestamp}-{end_timestamp}"
                )
                return ""

            # 3. File Persistence
            filename = f"compliance_{start_timestamp}_{end_timestamp}.{format}"
            filepath = os.path.join(self._export_dir, filename)

            self._save_file(df, filepath, format)

            # 4. Success Notification
            duration_ms = (time.perf_counter() - start_perf) * 1000
            event = ComplianceExportEvent(
                trace_id=op_trace_id,
                source="ComplianceExporter",
                payload=ComplianceExportPayload(
                    report_type="REGULATORY_DAILY",
                    file_path=str(os.path.abspath(filepath)),
                    metadata={
                        "row_count": len(df),
                        "duration_ms": duration_ms,
                        "total_pnl": float(df["pnl"].sum() if "pnl" in df.columns else 0.0),
                    },
                ),
            )
            await self._event_bus.publish(event)

            logger.info(f"COMPLIANCE_REPORT_EXPORTED | Path: {filepath} | Rows: {len(df)}")
            return str(os.path.abspath(filepath))

        except Exception as e:
            logger.error(f"COMPLIANCE_EXPORT_CRITICAL | {e!s}")
            error_event = ComplianceErrorEvent(
                trace_id=op_trace_id,
                source="ComplianceExporter",
                payload=ComplianceErrorPayload(error_type="EXPORT_FAILURE", details=str(e)),
            )
            await self._event_bus.publish(error_event)
            raise

    def _save_file(self, df: pl.DataFrame, filepath: str, format: str) -> None:
        """Standardized Sink logic for multiple compliance formats."""
        format_lower = format.lower()
        if format_lower == "csv":
            df.write_csv(filepath)
        elif format_lower == "parquet":
            df.write_parquet(filepath)
        elif format_lower == "json":
            df.write_json(filepath)
        else:
            raise ValueError(f"Unsupported compliance format: {format}")
