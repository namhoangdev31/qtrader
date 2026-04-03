from __future__ import annotations

from typing import Any

from qtrader.core.events import EventType, MarketEvent
from qtrader.data.pipeline.base import DataNormalizer


class UnifiedNormalizer(DataNormalizer):
    """Normalizes raw data from multiple venues (Coinbase, Binance) into MarketEvent.
    
    This implementation handles the venue-specific mapping logic centrally.
    """

    def normalize(self, raw_data: dict[str, Any]) -> MarketEvent:
        """
        Convert raw feed dictionary to a standardized MarketEvent.
        """
        venue = raw_data.get("venue", "unknown").lower()
        symbol = raw_data.get("symbol", "unknown")
        trace_id = raw_data.get("trace_id", "pending")
        
        if venue == "coinbase":
            return self._normalize_coinbase(raw_data)
        elif venue == "binance":
            return self._normalize_binance(raw_data)
        else:
            # Fallback/Generic mapping
            return MarketEvent(
                type=EventType.MARKET_DATA,
                symbol=symbol,
                trace_id=trace_id,
                data=raw_data,
                metadata={"venue": venue}
            )

    def _normalize_coinbase(self, data: dict[str, Any]) -> MarketEvent:
        return MarketEvent(
            type=EventType.MARKET_DATA,
            symbol=data.get("symbol", "unknown"),
            seq_id=data.get("seq_id"),
            trace_id=data.get("trace_id", "pending"),
            data={
                "venue": "coinbase",
                "bid": float(data.get("bid", 0.0)),
                "ask": float(data.get("ask", 0.0)),
                "last_price": float(data.get("last_price", 0.0)),
            },
            metadata={"venue": "coinbase"}
        )

    def _normalize_binance(self, data: dict[str, Any]) -> MarketEvent:
        raw_payload = data.get("data", {})
        return MarketEvent(
            type=EventType.MARKET_DATA,
            symbol=data.get("symbol", "unknown"),
            seq_id=data.get("seq_id"),
            trace_id=data.get("trace_id", "pending"),
            data={
                "venue": "binance",
                "bid": float(raw_payload.get("b", 0.0)),
                "ask": float(raw_payload.get("a", 0.0)),
                "last_price": float(raw_payload.get("c", 0.0)),
                "volume": float(raw_payload.get("v", 0.0)),
            },
            metadata={"venue": "binance"}
        )
