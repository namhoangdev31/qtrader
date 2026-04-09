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
        timestamp: datetime | int | float | None = None,
        sl: float = 0.0,
        tp: float = 0.0,
        reason: str = "SIGNAL",
    ) -> None:
        """
        Log a trade execution in the unified institutional format.

        Args:
            symbol: Trading symbol
            side: 'BUY' or 'SELL'
            quantity: Executed quantity
            price: Execution price
            trace_id: The trace ID associated with the originating signal/tick
            timestamp: Execution timestamp (datetime, int microseconds, or float seconds)
            sl: Stop loss price (optional)
            tp: Take profit price (optional)
            reason: Execution reason
        """
        # Handle timestamp variants: int (micros), float (seconds), datetime
        ts: datetime
        if timestamp is None:
            ts = datetime.utcnow()
        elif isinstance(timestamp, datetime):
            ts = timestamp
        elif isinstance(timestamp, (int, float)):
            # Heuristic: if > 1e12, it's likely microseconds (as in BaseEvent)
            if timestamp > 1e12:
                ts = datetime.fromtimestamp(timestamp / 1_000_000)
            else:
                ts = datetime.fromtimestamp(timestamp)
        else:
            ts = datetime.utcnow()

        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Format: [TRADE] {timestamp} | {symbol} {side} {qty}@{price} | SL={sl} TP={tp} | Reason: {reason}
        log_msg = f"[TRADE] {ts_str} | {symbol} {side} {quantity}@{price} | SL={sl} TP={tp} | Reason: {reason}"

        # Log to loguru with trade context and forensic trace_id
        logger.bind(trade=True, trace_id=trace_id).info(log_msg)
