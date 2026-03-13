from datetime import datetime
from typing import Any

from qtrader.core.event import MarketDataEvent
from qtrader.data.pipeline.base import DataNormalizer


class OHLCVNormalizer(DataNormalizer):
    """Normalizes raw dictionary data into MarketDataEvent."""

    def __init__(self, symbol: str, column_mapping: dict[str, str] | None = None) -> None:
        self.symbol = symbol
        self.column_mapping = column_mapping or {
            "timestamp": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }

    def normalize(self, raw_data: dict[str, Any]) -> MarketDataEvent:
        # Map raw columns to standard fields
        data = {
            std: raw_data.get(raw) for std, raw in self.column_mapping.items()
        }
        
        # Parse timestamp if it's a string
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now()

        return MarketDataEvent(
            symbol=self.symbol,
            data=data,
            timestamp=ts
        )
