from __future__ import annotations

from typing import TYPE_CHECKING, cast

import polars as pl

from qtrader.core.events import (
    BenchmarkComparisonEvent,
    BenchmarkComparisonPayload,
    BenchmarkErrorEvent,
    BenchmarkErrorPayload,
    DecisionTraceEvent,
    EventType,
    FillEvent,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from uuid import UUID

    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import BaseEvent
    from qtrader.data.datalake import DataLake


class ExecutionBenchmark:
    """
    Quantitative Analyst engine for execution benchmarking.
    
    Compares trade execution results against industrial benchmarks:
    - VWAP: Volume Weighted Average Price.
    - TWAP: Time Weighted Average Price.
    - Arrival Price: Mid-price at the moment of decision.
    """

    def __init__(self, event_bus: EventBus, datalake: DataLake) -> None:
        """
        Initialize the benchmarking engine with data source and bus hooks.
        """
        self._event_bus = event_bus
        self._datalake = datalake

    async def benchmark_trade_lifecycle(
        self, trace_id: UUID, events: list[BaseEvent]
    ) -> BenchmarkComparisonEvent | None:
        """
        Aggregate fills and compare against market data benchmarks.
        
        Args:
            trace_id: Global correlation ID for the trade.
            events: Chronological stream of events for the trace.
        """
        try:
            # 1. Extraction: Identify decision and execution window
            decision_event = next(
                (e for e in events if e.event_type == EventType.DECISION_TRACE), None
            )
            fill_events = [
                e
                for e in events
                if e.event_type == EventType.FILL and isinstance(e, FillEvent)
            ]

            if not decision_event or not isinstance(decision_event, DecisionTraceEvent):
                return None

            if not fill_events:
                return None

            d_payload = decision_event.payload
            symbol = fill_events[0].payload.symbol
            side = d_payload.decision
            arrival_price = d_payload.decision_price

            # Weighted average execution price
            total_qty = sum(f.payload.quantity for f in fill_events)
            weighted_sum = sum(f.payload.price * f.payload.quantity for f in fill_events)
            avg_exec_price = float(weighted_sum / total_qty)

            # Window: from decision to last fill
            start_ts = decision_event.timestamp
            end_ts = max(f.timestamp for f in fill_events)

            # 2. Benchmarking: Retrieval of Market Data
            try:
                df_market = self._datalake.load_data(symbol, "1m")

                if df_market.is_empty():
                    vwap = arrival_price
                    twap = arrival_price
                else:
                    # Filter for the execution window
                    ts_col = pl.col("timestamp")
                    df_window = df_market.filter((ts_col >= start_ts) & (ts_col <= end_ts))

                    if df_window.is_empty():
                        vwap = arrival_price
                        twap = arrival_price
                    else:
                        # Compute Benchmarks
                        # VWAP = Σ(P * V) / Σ V
                        v_sum = cast("float", df_window["volume"].sum())
                        if v_sum > 0:
                            p_v_series = df_window["close"] * df_window["volume"]
                            vwap = cast("float", p_v_series.sum()) / v_sum
                        else:
                            c_m = df_window["close"].mean()
                            vwap = cast("float", c_m) if c_m is not None else arrival_price

                        # TWAP = Σ P / N
                        c_m = df_window["close"].mean()
                        twap = cast("float", c_m) if c_m is not None else arrival_price

            except Exception as e:
                logger.warning(f"BENCHMARK_MARKET_DATA_MISSING | {symbol} | {e!s}")
                await self._emit_error(trace_id, "MISSING_HISTORICAL_DATA", str(e))
                return None

            # 3. Performance Metrics
            perf_vwap = avg_exec_price - vwap
            perf_twap = avg_exec_price - twap

            # 4. Result Broadcasting
            event = BenchmarkComparisonEvent(
                trace_id=trace_id,
                source="ExecutionBenchmarkEngine",
                payload=BenchmarkComparisonPayload(
                    trace_id=trace_id,
                    exec_price=avg_exec_price,
                    vwap=vwap,
                    twap=twap,
                    arrival_price=arrival_price,
                    perf_vwap=perf_vwap,
                    perf_twap=perf_twap,
                    side=side,
                    metadata={
                        "window_duration_ms": (end_ts - start_ts) / 1000,
                        "fill_count": len(fill_events),
                    },
                ),
            )

            await self._event_bus.publish(event)
            logger.info(
                f"BENCHMARK_COMPLETED | trace_id: {trace_id} | VWAP_DIFF: {perf_vwap:.4f}"
            )

            return event

        except Exception as e:
            logger.error(f"BENCHMARK_ENGINE_FAILURE | {e!s}")
            await self._emit_error(trace_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, trace_id: UUID, err_type: str, details: str) -> None:
        error_event = BenchmarkErrorEvent(
            trace_id=trace_id,
            source="ExecutionBenchmarkEngine",
            payload=BenchmarkErrorPayload(error_type=err_type, details=details),
        )
        await self._event_bus.publish(error_event)
