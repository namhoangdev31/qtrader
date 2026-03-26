from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

import polars as pl

from qtrader.core.events import (
    BenchmarkComparisonEvent,
    CostAttributionEvent,
    ImplementationShortfallEvent,
    SlippageBreakdownEvent,
    TCAReportErrorEvent,
    TCAReportErrorPayload,
    TCAReportEvent,
    TCAReportPayload,
    VenueRankingEvent,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import BaseEvent


class TCAReportGenerator:
    """
    Global TCA Reporting Engine for institutional-grade audit appraisal.

    Aggregates metrics from IS, Slippage, Benchmarking, and Attribution:
    - Average Shortfall / Slippage / VWAP diff.
    - Global cost component attribution.
    - Performance ranking of liquidity venues.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the reporting generator with global bus hooks.
        """
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def generate_global_report(
        self, events: list[BaseEvent], period_start: int, period_end: int
    ) -> TCAReportEvent | None:
        """
        Consolidate all historical TCA vectors into a single structural report.
        """
        try:
            if not events:
                await self._emit_error("EMPTY_DATASET", "No events provided.")
                return None

            # 1. Metric Aggregation using Polars
            data = []
            attributions = []
            best_venue = "UNKNOWN"

            for event in events:
                if isinstance(event, ImplementationShortfallEvent):
                    data.append({"type": "IS", "val": float(event.payload.total_cost)})
                elif isinstance(event, SlippageBreakdownEvent):
                    data.append({"type": "SLIP", "val": float(event.payload.total_slippage)})
                elif isinstance(event, BenchmarkComparisonEvent):
                    data.append({"type": "VWAP", "val": float(event.payload.perf_vwap)})
                elif isinstance(event, CostAttributionEvent):
                    p = event.payload
                    attributions.append(
                        {
                            "impact": p.impact_pct,
                            "timing": p.timing_pct,
                            "fees": p.fee_pct,
                            "funding": p.funding_pct,
                        }
                    )
                elif isinstance(event, VenueRankingEvent):
                    if event.payload.rank == 1:
                        best_venue = event.payload.venue

            if not data:
                await self._emit_error("INSUFFICIENT_METRICS", "No shortfall/slippage data.")
                return None

            df = pl.DataFrame(data)

            # Weighted Averages (assuming uniform trade weight for now)
            df_is = df.filter(pl.col("type") == "IS")
            df_slip = df.filter(pl.col("type") == "SLIP")
            df_vwap = df.filter(pl.col("type") == "VWAP")

            avg_is = cast("float", df_is["val"].mean() if not df_is.is_empty() else 0.0)
            avg_slip = cast("float", df_slip["val"].mean() if not df_slip.is_empty() else 0.0)
            vwap_diff = cast("float", df_vwap["val"].mean() if not df_vwap.is_empty() else 0.0)
            total_cost = cast("float", df_is["val"].sum() if not df_is.is_empty() else 0.0)
            trade_count = int(df_is.height)

            # 2. Attribution Aggregation
            if attributions:
                df_attr = pl.DataFrame(attributions)
                cost_breakdown = {
                    "impact": cast("float", df_attr["impact"].mean() or 0.0),
                    "timing": cast("float", df_attr["timing"].mean() or 0.0),
                    "fees": cast("float", df_attr["fees"].mean() or 0.0),
                    "funding": cast("float", df_attr["funding"].mean() or 0.0),
                }
            else:
                cost_breakdown = {}

            # 3. Report Event Creation
            report = TCAReportEvent(
                trace_id=self._system_trace,
                source="TCAReportGenerator",
                payload=TCAReportPayload(
                    period_start=period_start,
                    period_end=period_end,
                    avg_shortfall=avg_is,
                    avg_slippage=avg_slip,
                    vwap_diff=vwap_diff,
                    cost_breakdown=cost_breakdown,
                    best_venue=best_venue,
                    total_cost=total_cost,
                    trade_count=trade_count,
                ),
            )

            await self._event_bus.publish(report)
            logger.info(f"TCA_REPORT_GENERATED | TradeCount: {trade_count}")

            return report

        except Exception as e:
            logger.error(f"TCA_REPORT_FAILURE | {e!s}")
            await self._emit_error("SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, err_type: str, details: str) -> None:
        """Emit a TCAReportErrorEvent to the global bus."""
        error_event = TCAReportErrorEvent(
            trace_id=self._system_trace,
            source="TCAReportGenerator",
            payload=TCAReportErrorPayload(error_type=err_type, details=details),
        )
        await self._event_bus.publish(error_event)
