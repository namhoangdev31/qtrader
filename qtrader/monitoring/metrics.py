from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

# Minimum samples needed for a stable 95% VaR estimate
_VAR_MIN_SAMPLES = 20


@dataclass
class TradeMetrics:
    """Consolidated trade metrics."""

    total_fills: int = 0
    total_orders: int = 0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    avg_price: float = 0.0


@dataclass
class PnLMetrics:
    """Consolidated PnL metrics."""

    total_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    daily_pnl: float = 0.0


@dataclass
class RiskMetrics:
    """Consolidated risk metrics."""

    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    var_95: float = 0.0  # 95% Value at Risk
    risk_alerts: int = 0


@dataclass
class LatencyMetrics:
    """Consolidated latency metrics (all in ms)."""

    avg_ack_latency: float = 0.0
    avg_fill_latency: float = 0.0
    last_update_ms: float = 0.0


class MetricsAggregator:
    """
    High-performance aggregator for real-time trading metrics.
    Optimized for sub-1-ms updates via in-memory vector calculations.
    """

    def __init__(self, window_size: int = 1000) -> None:
        """
        Args:
            window_size: Number of events to keep for rolling calculations (e.g., VaR).
        """
        self.window_size = window_size
        self.pnl = PnLMetrics()
        self.risk = RiskMetrics()
        self.latency = LatencyMetrics()
        self.trades = TradeMetrics()

        # Internal state for rolling window calculations
        self._nav_history: list[float] = []
        self._peak_nav: float = 0.0
        self._returns: list[float] = []

        # Latency tracking
        self._ack_latencies: list[float] = []
        self._fill_latencies: list[float] = []

    def on_fill(self, symbol: str, quantity: float, price: float, side: str) -> None:
        """Update trade metrics on a trade fill."""
        self.trades.total_fills += 1
        if side.upper() == "BUY":
            self.trades.buy_volume += quantity * price
        else:
            self.trades.sell_volume += quantity * price
            
        # Update rolling average fill price
        total_vol = self.trades.buy_volume + self.trades.sell_volume
        if total_vol > 0:
            self.trades.avg_price = total_vol / self.trades.total_fills

    def on_order(self, symbol: str, quantity: float, side: str) -> None:
        """Update order count."""
        self.trades.total_orders += 1

    def on_risk_alert(self) -> None:
        """Record a risk limit breach or alert."""
        self.risk.risk_alerts += 1

    def update_pnl(self, nav: float, realized: float = 0.0) -> None:
        """
        Update PnL and Drawdown based on new NAV.
        """
        if not self._nav_history:
            self._peak_nav = nav
            self.pnl.daily_pnl = 0.0
        else:
            prev_nav = self._nav_history[-1]
            ret = (nav - prev_nav) / prev_nav if prev_nav != 0 else 0.0
            self._returns.append(ret)
            self.pnl.daily_pnl = nav - self._nav_history[0]  # Assuming first is start of day

            if len(self._returns) > self.window_size:
                self._returns.pop(0)

        self._nav_history.append(nav)
        if len(self._nav_history) > self.window_size:
            self._nav_history.pop(0)

        # Update PnL
        self.pnl.total_pnl = nav - self._nav_history[0]
        self.pnl.realized_pnl += realized
        self.pnl.unrealized_pnl = self.pnl.total_pnl - self.pnl.realized_pnl

        # Update Drawdown
        self._peak_nav = max(self._peak_nav, nav)

        if self._peak_nav > 0:
            self.risk.current_drawdown = (self._peak_nav - nav) / self._peak_nav
            self.risk.max_drawdown = max(self.risk.max_drawdown, self.risk.current_drawdown)

        # Update VaR (Simple historical VaR)
        if len(self._returns) >= _VAR_MIN_SAMPLES:
            self.risk.var_95 = float(np.percentile(self._returns, 5))

    def record_latency(self, stage: str, latency_ms: float) -> None:
        """
        Record latency between order lifecycle stages.
        """
        self.latency.last_update_ms = latency_ms

        if stage == "ack":
            self._ack_latencies.append(latency_ms)
            if len(self._ack_latencies) > self.window_size:
                self._ack_latencies.pop(0)
            self.latency.avg_ack_latency = float(np.mean(self._ack_latencies))

        elif stage == "fill":
            self._fill_latencies.append(latency_ms)
            if len(self._fill_latencies) > self.window_size:
                self._fill_latencies.pop(0)
            self.latency.avg_fill_latency = float(np.mean(self._fill_latencies))

    def get_summary(self) -> dict[str, Any]:
        """
        Return a summary dictionary of all current metrics.
        """
        summary: dict[str, Any] = {
            "pnl": {
                "total": self.pnl.total_pnl,
                "realized": self.pnl.realized_pnl,
                "unrealized": self.pnl.unrealized_pnl,
                "daily": self.pnl.daily_pnl,
            },
            "risk": {
                "max_drawdown": self.risk.max_drawdown,
                "current_drawdown": self.risk.current_drawdown,
                "var_95": self.risk.var_95,
                "alerts": self.risk.risk_alerts,
            },
            "latency": {
                "avg_ack": self.latency.avg_ack_latency,
                "avg_fill": self.latency.avg_fill_latency,
                "last": self.latency.last_update_ms,
            },
            "trades": {
                "fills": self.trades.total_fills,
                "orders": self.trades.total_orders,
                "buy_v": self.trades.buy_volume,
                "sell_v": self.trades.sell_volume,
                "avg_p": self.trades.avg_price,
            },
            "timestamp": datetime.now().isoformat(),
        }
        return summary
