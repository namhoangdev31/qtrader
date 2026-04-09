from __future__ import annotations
import time
from typing import TYPE_CHECKING, Any, cast
import numpy as np
import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import MarketEvent
MIN_WINDOW_SIZE = 10


class DataQualityError(Exception):
    pass


class DataQualityGate:
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
        current_price = event.close
        if len(recent_prices) >= MIN_WINDOW_SIZE:
            median = float(np.median(recent_prices))
            mad = float(np.median(np.abs(np.array(recent_prices) - median)))
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
        logger.warning(f"DataQualityGate: Rejected {event.symbol} - {reason}")
        if self.event_bus:
            pass

    @staticmethod
    def check_outlier(series: pl.Series, method: str = "zscore", threshold: float = 3.0) -> None:
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
        try:
            val = float(ts_ms)
            age_ms = time.time() * 1000 - val
            if age_ms > max_age_ms:
                raise DataQualityError(f"Stale data: {age_ms:.0f}ms old")
        except (ValueError, TypeError) as e:
            raise DataQualityError(f"Invalid timestamp format: {e}") from e

    @staticmethod
    def check_trade_quote_mismatch(
        trade_price: float, best_bid: float, best_ask: float, max_spread_pct: float = 0.1
    ) -> tuple[bool, str]:
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            return (True, "Invalid spread — skip check")
        best_ask - best_bid
        mid = (best_bid + best_ask) / 2.0
        if trade_price < best_bid:
            deviation = (best_bid - trade_price) / mid
            if deviation > max_spread_pct:
                return (
                    False,
                    f"Trade below bid: {trade_price} < {best_bid} (deviation: {deviation:.2%})",
                )
        elif trade_price > best_ask:
            deviation = (trade_price - best_ask) / mid
            if deviation > max_spread_pct:
                return (
                    False,
                    f"Trade above ask: {trade_price} > {best_ask} (deviation: {deviation:.2%})",
                )
        return (True, "Within spread")
