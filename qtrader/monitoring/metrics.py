from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


class MetricsAggregator:
    def __init__(self) -> None:
        self._fill_count: int = 0
        self._order_count: int = 0
        self._risk_alert_count: int = 0
        self._total_volume: float = 0.0
        self._total_notional: float = 0.0
        self._pnl_realized: float = 0.0
        self._nav: float = 0.0
        self._symbol_fills: dict[str, int] = defaultdict(int)
        self._symbol_volume: dict[str, float] = defaultdict(float)
        self._last_update: datetime = datetime.now(timezone.utc)

    def on_fill(self, symbol: str, quantity: float, price: float, side: str) -> None:
        self._fill_count += 1
        self._total_volume += quantity
        self._total_notional += quantity * price
        self._symbol_fills[symbol] += 1
        self._symbol_volume[symbol] += quantity
        self._last_update = datetime.now(timezone.utc)

    def on_order(self, symbol: str, quantity: float, side: str) -> None:
        self._order_count += 1
        self._last_update = datetime.now(timezone.utc)

    def on_risk_alert(self) -> None:
        self._risk_alert_count += 1
        self._last_update = datetime.now(timezone.utc)

    def update_pnl(self, nav: float, realized: float = 0.0) -> None:
        self._nav = nav
        self._pnl_realized = realized
        self._last_update = datetime.now(timezone.utc)

    def get_summary(self) -> dict[str, Any]:
        return {
            "fill_count": self._fill_count,
            "order_count": self._order_count,
            "risk_alert_count": self._risk_alert_count,
            "total_volume": self._total_volume,
            "total_notional": self._total_notional,
            "pnl_realized": self._pnl_realized,
            "nav": self._nav,
            "symbol_fills": dict(self._symbol_fills),
            "symbol_volume": dict(self._symbol_volume),
            "last_update": self._last_update.isoformat(),
        }
