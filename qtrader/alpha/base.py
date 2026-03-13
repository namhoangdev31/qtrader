from typing import Protocol, runtime_checkable

import polars as pl

from qtrader.core.event import MarketDataEvent, SignalEvent


@runtime_checkable
class AlphaModel(Protocol):
    """Protocol for alpha generation logic."""

    def on_market_data(self, event: MarketDataEvent) -> list[SignalEvent]:
        """Process market data and return potential signals."""
        ...


class BaseAlphaModel:
    """Base class for alpha models with helper methods."""

    _MAX_HISTORY = 1000

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.data_history: list[MarketDataEvent] = []

    def update_history(self, event: MarketDataEvent) -> None:
        if event.symbol == self.symbol:
            self.data_history.append(event)
            # Keep history manageable
            if len(self.data_history) > self._MAX_HISTORY:
                self.data_history.pop(0)

    def get_history_df(self) -> pl.DataFrame:
        if not self.data_history:
            return pl.DataFrame()
        
        dicts = [e.data for e in self.data_history]
        return pl.DataFrame(dicts)
