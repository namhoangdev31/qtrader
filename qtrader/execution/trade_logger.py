"""Standardized trade logging for institutional audit trails."""
from __future__ import annotations

from datetime import datetime

from loguru import logger


class TradeLogger:
    """
    Standardized logger for all trade entries and fills.
    Format: [ts][trace_id][symbol][side][qty][price]
    """

    @staticmethod
    def log_trade(
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        trace_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        """
        Log a trade execution in the unified institutional format.
        
        Args:
            symbol: Trading symbol
            side: 'BUY' or 'SELL'
            quantity: Executed quantity
            price: Execution price
            trace_id: The trace ID associated with the originating signal/tick
            timestamp: Execution timestamp (defaults to now)
        """
        ts = timestamp or datetime.utcnow()
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Format: [ts][trace_id][symbol][side][qty][price]
        log_msg = f"[{ts_str}][{trace_id}][{symbol}][{side}][{quantity}][{price}]"
        
        # Log to loguru with trade context
        logger.bind(trade=True, trace_id=trace_id).info(f"[TRADE]{log_msg}")
