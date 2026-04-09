from __future__ import annotations

from datetime import datetime

from loguru import logger


class TradeLogger:
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
        ts: datetime
        if timestamp is None:
            ts = datetime.utcnow()
        elif isinstance(timestamp, datetime):
            ts = timestamp
        elif isinstance(timestamp, (int, float)):
            if timestamp > 1000000000000.0:
                ts = datetime.fromtimestamp(timestamp / 1000000)
            else:
                ts = datetime.fromtimestamp(timestamp)
        else:
            ts = datetime.utcnow()
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_msg = f"[TRADE] {ts_str} | {symbol} {side} {quantity}@{price} | SL={sl} TP={tp} | Reason: {reason}"
        logger.bind(trade=True, trace_id=trace_id).info(log_msg)
