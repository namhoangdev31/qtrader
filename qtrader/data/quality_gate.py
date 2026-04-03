from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from qtrader.core.events import MarketEvent
    from qtrader.core.event_bus import EventBus

MIN_WINDOW_SIZE = 10


class DataQualityError(Exception):
    """Exception raised when data quality checks fail."""

    pass


class DataQualityGate:
    """Implement robust statistical filtering and validation layer.

    Order:
    1. Outlier Detection (MAD)
    2. Cross-Exchange Validation
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def validate(
        self,
        event: MarketEvent,
        recent_prices: list[float],
        ref_price: float | None = None,
        z_threshold: float = 3.0,
        epsilon_pct: float = 0.05,
    ) -> bool:
        """Run all quality checks on a single MarketEvent.

        Args:
            event: The candidate event.
            recent_prices: Rolling price window from EventStore.
            ref_price: Reference price from another venue (optional).
            z_threshold: Z-score limit (MAD).
            epsilon_pct: Cross-exchange deviation limit (e.g., 0.05 = 5%).

        Returns:
            True if valid, False if rejected.
        """
        current_price = event.close

        # 1. Outlier Detection (MAD)
        if len(recent_prices) >= MIN_WINDOW_SIZE:
            median = float(np.median(recent_prices))
            mad = float(np.median(np.abs(np.array(recent_prices) - median)))

            # Use MAD instead of standard deviation for robustness against outliers
            if mad > 0:
                z_score = abs(current_price - median) / mad
                if z_score > z_threshold:
                    self._reject(
                        event,
                        f"Outlier detected (MAD Z-score: {z_score:.2f})",
                        current_price,
                        z_threshold,
                    )
                    return False

        # 2. Cross-Exchange Validation
        if ref_price is not None and ref_price > 0:
            deviation_pct = abs(current_price - ref_price) / ref_price
            if deviation_pct > epsilon_pct:
                self._reject(
                    event,
                    f"Cross-exchange deviation too high: {deviation_pct:.2%}",
                    current_price,
                    epsilon_pct,
                )
                return False

        return True

    def _reject(self, event: MarketEvent, reason: str, value: float, threshold: float) -> None:
        """Log rejection and emit DataRejectedEvent."""
        logger.warning(f"DataQualityGate: Rejected {event.symbol} - {reason}")

        if self.event_bus:
            # Rejection is logged here, but the DataRejectedEvent
            # is emitted by the orchestrator which is the async context.
            pass

    @staticmethod
    def check_outlier(series: pl.Series, method: str = "zscore", threshold: float = 3.0) -> None:
        """Legacy outlier check using standard deviation."""
        if series.is_empty():
            return
        mean = series.mean()
        std = series.std()
        if mean is None or std is None or std == 0:
            return
        z = (series.cast(pl.Float64) - mean) / std
        z_max = float(cast("float", z.abs().max() or 0.0))
        if z_max > threshold:
            raise DataQualityError(f"Outlier detected: max |z| = {z_max:.2f}")

    @staticmethod
    def check_stale(ts_ms: Any, max_age_ms: float = 5000.0) -> None:
        """Check if timestamp is too old."""
        try:
            val = float(ts_ms)
            age_ms = (time.time() * 1000) - val
            if age_ms > max_age_ms:
                raise DataQualityError(f"Stale data: {age_ms:.0f}ms old")
        except (ValueError, TypeError) as e:
            raise DataQualityError(f"Invalid timestamp format: {e}") from e

    @staticmethod
    def check_trade_quote_mismatch(
        trade_price: float,
        best_bid: float,
        best_ask: float,
        max_spread_pct: float = 0.10,
    ) -> tuple[bool, str]:
        """Standash §4.1: Validate trade price is within bid-ask spread.

        A trade executed outside the NBBO (National Best Bid and Offer)
        indicates data quality issues or potential market manipulation.

        Args:
            trade_price: Executed trade price.
            best_bid: Current best bid price.
            best_ask: Current best ask price.
            max_spread_pct: Maximum allowed deviation from spread as fraction.

        Returns:
            (is_valid, reason) tuple.
        """
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            return True, "Invalid spread — skip check"

        spread = best_ask - best_bid
        mid = (best_bid + best_ask) / 2.0

        # Trade should be within the spread (or very close to it)
        if trade_price < best_bid:
            deviation = (best_bid - trade_price) / mid
            if deviation > max_spread_pct:
                return False, (
                    f"Trade below bid: {trade_price} < {best_bid} (deviation: {deviation:.2%})"
                )
        elif trade_price > best_ask:
            deviation = (trade_price - best_ask) / mid
            if deviation > max_spread_pct:
                return False, (
                    f"Trade above ask: {trade_price} > {best_ask} (deviation: {deviation:.2%})"
                )

        return True, "Within spread"
