import uuid
from unittest.mock import AsyncMock, patch

import pytest

from qtrader.core.events import (
    BenchmarkComparisonEvent,
    BenchmarkComparisonPayload,
    CostAttributionEvent,
    CostAttributionPayload,
    EventType,
    ImplementationShortfallEvent,
    ImplementationShortfallPayload,
    SlippageBreakdownEvent,
    SlippageBreakdownPayload,
    TCAReportEvent,
    VenueRankingEvent,
    VenueRankingPayload,
)
from qtrader.tca.tca_report import TCAReportGenerator

# Test Constants
SYSTEM_TRACE = "00000000-0000-0000-0000-000000000000"


@pytest.mark.asyncio
async def test_tca_report_generation_success() -> None:
    """Verify that all TCA metrics are correctly aggregated into a global report."""
    bus = AsyncMock()
    generator = TCAReportGenerator(bus)

    trace_id_1 = uuid.uuid4()
    trace_id_2 = uuid.uuid4()

    events = [
        # Trade 1
        ImplementationShortfallEvent(
            trace_id=trace_id_1,
            source="IS",
            timestamp=100,
            payload=ImplementationShortfallPayload(
                trace_id=trace_id_1,
                decision_price=50.0,
                executed_price=50.05,
                quantity=100.0,
                shortfall=5.0,
                total_cost=6.0,
                side="BUY",
            ),
        ),
        SlippageBreakdownEvent(
            trace_id=trace_id_1,
            source="Slip",
            timestamp=101,
            payload=SlippageBreakdownPayload(
                trace_id=trace_id_1,
                total_slippage=6.0,
                market_impact=3.0,
                timing_cost=2.0,
                fees=1.0,
            ),
        ),
        # Trade 2 (higher cost)
        ImplementationShortfallEvent(
            trace_id=trace_id_2,
            source="IS",
            timestamp=200,
            payload=ImplementationShortfallPayload(
                trace_id=trace_id_2,
                decision_price=60.0,
                executed_price=60.1,
                quantity=100.0,
                shortfall=10.0,
                total_cost=12.0,
                side="BUY",
            ),
        ),
        # Benchmark Comparisons
        BenchmarkComparisonEvent(
            trace_id=trace_id_1,
            source="Bench",
            timestamp=105,
            payload=BenchmarkComparisonPayload(
                trace_id=trace_id_1,
                exec_price=50.05,
                vwap=50.02,
                twap=50.03,
                arrival_price=50.0,
                perf_vwap=0.03,
                perf_twap=0.02,
                side="BUY",
            ),
        ),
        # Cost Attribution
        CostAttributionEvent(
            trace_id=trace_id_1,
            source="Attr",
            timestamp=110,
            payload=CostAttributionPayload(
                trace_id=trace_id_1,
                total_cost=6.0,
                impact_pct=0.5,
                timing_pct=0.33,
                fee_pct=0.17,
                funding_pct=0.0,
            ),
        ),
        # Venue Ranking
        VenueRankingEvent(
            trace_id=uuid.UUID(SYSTEM_TRACE),
            source="Venue",
            timestamp=500,
            payload=VenueRankingPayload(
                venue="BINANCE", score=0.4, rank=1, metrics={"avg_is": 0.4}
            ),
        ),
    ]

    # Generate report
    report = await generator.generate_global_report(events, 0, 1000)

    assert report is not None  # noqa: S101
    assert isinstance(report, TCAReportEvent)  # noqa: S101
    assert report.payload.trade_count == 2  # noqa: S101, PLR2004
    assert report.payload.avg_shortfall == pytest.approx(9.0)  # (6+12)/2 # noqa: S101
    assert report.payload.best_venue == "BINANCE"  # noqa: S101
    assert "impact" in report.payload.cost_breakdown  # noqa: S101


@pytest.mark.asyncio
async def test_tca_report_generation_incomplete() -> None:
    """Verify error emission for datasets missing core diagnostic metrics."""
    bus = AsyncMock()
    generator = TCAReportGenerator(bus)

    # 1. Empty events
    report = await generator.generate_global_report([], 0, 1000)
    assert report is None  # noqa: S101
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.TCA_REPORT_ERROR  # noqa: S101
    assert bus.publish.call_args[0][0].payload.error_type == "EMPTY_DATASET"  # noqa: S101

    # 2. Insufficient metrics (only VenueRanking, no IS/Slip)
    bus.reset_mock()
    events = [
        VenueRankingEvent(
            trace_id=uuid.UUID(SYSTEM_TRACE),
            source="S",
            timestamp=1,
            payload=VenueRankingPayload(venue="V", score=1, rank=1, metrics={}),
        )
    ]
    report = await generator.generate_global_report(events, 0, 1000)
    assert report is None  # noqa: S101
    assert bus.publish.call_args[0][0].payload.error_type == "INSUFFICIENT_METRICS"  # noqa: S101


@pytest.mark.asyncio
async def test_tca_report_generation_system_failure() -> None:
    """Verify industrial error handling during system-level exceptions."""
    bus = AsyncMock()
    generator = TCAReportGenerator(bus)

    # Force exception inside the loop using patch on isinstance
    # This is a bit hacky but guarantees hitting the except block.
    with patch("qtrader.tca.tca_report.isinstance", side_effect=Exception("SIMULATED_FAILURE")):
        report = await generator.generate_global_report([AsyncMock()], 0, 1)

    assert report is None  # noqa: S101
    assert bus.publish.called  # noqa: S101
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)  # noqa: S101
