from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, TypedDict, cast
from uuid import UUID

import polars as pl

from qtrader.core.events import (
    ImplementationShortfallEvent,
    SlippageBreakdownEvent,
    VenueRankingEvent,
    VenueRankingPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import BaseEvent


class VenueStat(TypedDict):
    """Internal structure for venue performance statistics."""
    venue: str
    score: float
    metrics: dict[str, float]
    samples: int


class VenueRankingEngine:
    """
    Quantitative Execution Strategist engine for venue ranking.
    
    Evaluates exchanges based on weighted TCA performance:
    1. Implementation Shortfall (IS)
    2. Total Slippage
    3. Timing Cost
    
    Uses a rolling window of samples to ensure non-stale profiles.
    """

    def __init__(
        self, 
        event_bus: EventBus, 
        window_size: int = 100,
        weights: dict[str, float] | None = None
    ) -> None:
        """
        Initialize the ranking engine with weights and window constraints.
        """
        self._event_bus = event_bus
        self._window_size = window_size
        self._weights = weights or {"is": 0.4, "slippage": 0.4, "timing": 0.2}
        self._history: dict[str, deque[dict[str, float | str]]] = {}
        
        # System-level trace ID for ranking broadcasts
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def process_tca_results(
        self, 
        events: list[BaseEvent]
    ) -> list[VenueRankingEvent]:
        """
        Update rolling performance profiles for all identified venues.
        """
        try:
            per_venue_data: dict[str, list[dict[str, float | str]]] = {}
            
            for event in events:
                # Group metrics by the venue metadata tag
                venue = str(event.payload.metadata.get("venue", "UNKNOWN"))
                
                if venue == "UNKNOWN":
                    continue
                
                if venue not in per_venue_data:
                    per_venue_data[venue] = []
                
                if isinstance(event, ImplementationShortfallEvent):
                    per_venue_data[venue].append({
                        "type": "IS", "val": float(event.payload.total_cost)
                    })
                elif isinstance(event, SlippageBreakdownEvent):
                    per_venue_data[venue].append({
                        "type": "SLIP", "val": float(event.payload.total_slippage),
                        "timing": float(event.payload.timing_cost)
                    })

            for venue, components in per_venue_data.items():
                if venue not in self._history:
                    self._history[venue] = deque(maxlen=self._window_size)
                for comp in components:
                     self._history[venue].append(comp)

            return await self._compute_rankings()

        except Exception as e:
            logger.error(f"VENUE_RANKING_FAILURE | {e!s}")
            return []

    async def _compute_rankings(self) -> list[VenueRankingEvent]:
        """
        Compute aggregate scores and emit optimized venue ranks.
        """
        venue_stats: list[VenueStat] = []
        
        for venue, history in self._history.items():
            if not history:
                continue
            
            # Efficiently Aggregate Rolling Window Cost Vectors
            df = pl.DataFrame(list(history))
            df_is = df.filter(pl.col("type") == "IS")
            df_slip = df.filter(pl.col("type") == "SLIP")
            
            # Require at least one sample of each type for a valid score
            if df_is.is_empty() or df_slip.is_empty():
                continue
                
            avg_is = cast("float", df_is["val"].mean() or 0.0)
            avg_slippage = cast("float", df_slip["val"].mean() or 0.0)
            avg_timing = cast("float", df_slip["timing"].mean() or 0.0)
            
            # Score = Weighted Multi-factor Cost (Lower Cost => Higher Rank)
            score = (
                self._weights["is"] * avg_is +
                self._weights["slippage"] * avg_slippage +
                self._weights["timing"] * avg_timing
            )
            
            venue_stats.append({
                "venue": venue,
                "score": score,
                "metrics": {
                    "avg_is": avg_is,
                    "avg_slippage": avg_slippage,
                    "avg_timing": avg_timing
                },
                "samples": len(history)
            })

        if not venue_stats:
            return []

        # Sort venues by ascending cost score (best venue sits at Rank 1)
        venue_stats.sort(key=lambda x: x["score"])
        
        ranking_events: list[VenueRankingEvent] = []
        for rank, stat in enumerate(venue_stats, 1):
            event = VenueRankingEvent(
                trace_id=self._system_trace,
                source="VenueRankingEngine",
                payload=VenueRankingPayload(
                    venue=stat["venue"],
                    score=stat["score"],
                    rank=rank,
                    metrics=stat["metrics"],
                    metadata={"window_samples": stat["samples"]}
                )
            )
            
            await self._event_bus.publish(event)
            ranking_events.append(event)
            
        return ranking_events
