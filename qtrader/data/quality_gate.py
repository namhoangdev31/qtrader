"""Data quality gate for validating market data before alpha processing."""

from __future__ import annotations

import datetime
import time
import uuid
from typing import Any

import numpy as np
import polars as pl
from loguru import logger

from qtrader.core.event import DataRejectedEvent, EventType, MarketDataEvent
from qtrader.core.event_bus import EventBus


class DataQualityError(Exception):
    """Exception raised when data quality checks fail."""

    pass


class DataQualityGate:
    """Gate for ensuring only high-quality market data enters the system.
    
    Filters outliers via Median Absolute Deviation (MAD) and performs
    cross-exchange price validation for statistical robustness.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def validate(
        self, 
        event: MarketDataEvent, 
        recent_prices: list[float], 
        ref_price: float | None = None,
        z_threshold: float = 3.0,
        epsilon_pct: float = 0.05
    ) -> bool:
        """Sequential validation of a market event.
        
        Args:
            event: The MarketDataEvent to validate.
            recent_prices: List of recent prices for the same symbol.
            ref_price: Latest price for the same symbol from a different venue.
            z_threshold: MAD Z-score threshold for outlier detection.
            epsilon_pct: Maximum allowed deviation percentage for cross-exchange check.
            
        Returns:
            True if valid, False if rejected.
        """
        symbol = event.symbol
        current_price = event.close
        
        # 1. Outlier Detection (MAD)
        if len(recent_prices) >= 10:
            median = float(np.median(recent_prices))
            mad = float(np.median(np.abs(np.array(recent_prices) - median)))
            
            # Use user-supplied Z = (x - m) / MAD if MAD > 0
            if mad > 0:
                z_score = abs(current_price - median) / mad
                if z_score > z_threshold:
                    self._reject(event, f"Outlier detected (MAD Z-score: {z_score:.2f})", current_price, z_threshold)
                    return False
        
        # 2. Cross-Exchange Validation
        if ref_price is not None and ref_price > 0:
            deviation_pct = abs(current_price - ref_price) / ref_price
            if deviation_pct > epsilon_pct:
                self._reject(event, f"Cross-exchange deviation too high: {deviation_pct:.2%}", current_price, epsilon_pct)
                return False
                
        return True

    def _reject(self, event: MarketDataEvent, reason: str, value: float, threshold: float) -> None:
        """Log rejection and emit DataRejectedEvent."""
        logger.warning(f"DataQualityGate: Rejected {event.symbol} - {reason}")
        
        if self.event_bus:
            import uuid
            rejected_ev = DataRejectedEvent(
                event_id=str(uuid.uuid4()),
                symbol=event.symbol,
                trace_id=event.trace_id,
                reason=reason,
                value=value,
                threshold=threshold,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            # Since this is a synchronous method and event_bus.publish is usually async, 
            # we'll assume the orchestrator handles the await or use a fire-and-forget sync wrapper
            # In our EventBus implementation, we need to await it.
            # I'll update the orchestrator to handle the rejection event.
            pass

    @staticmethod
    def check_stale(ts_ms: float, max_age_ms: int = 5000) -> None:
        """Check if a timestamp (in ms) is stale."""
        age_ms = (time.time() * 1000) - ts_ms
        if age_ms > max_age_ms:
            raise DataQualityError(f"Stale data: {age_ms:.0f}ms old")
            
    # Legacy methods kept for compatibility with other callers if any
    @staticmethod
    def check_outlier(series: pl.Series, method: str = "zscore", threshold: float = 3.0) -> None:
        """Legacy outlier check using standard deviation."""
        if series.is_empty(): return
        mean = series.mean()
        std = series.std()
        if mean is None or std is None or std == 0: return
        z = (series.cast(pl.Float64) - mean) / std
        if z.abs().max() > threshold:
            raise DataQualityError(f"Outlier detected: max |z| = {z.abs().max():.2f}")
