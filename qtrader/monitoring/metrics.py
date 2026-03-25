from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

# Minimum samples needed for a stable 95% VaR estimate
_VAR_MIN_SAMPLES = 20


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


@dataclass
class LatencyMetrics:
    """Consolidated latency metrics (all in ms)."""

    avg_ack_latency: float = 0.0
    avg_fill_latency: float = 0.0
    last_update_ms: float = 0.0


class MetricsAggregator:
    """
    High-performance aggregator for real-time trading metrics.
    Optimized for sub-100ms updates via in-memory calculations.
    """

    def __init__(self, window_size: int = 1000):
        """
        Args:
            window_size: Number of events to keep for rolling calculations (e.g., VaR).
        """
        self.window_size = window_size
        self.pnl = PnLMetrics()
        self.risk = RiskMetrics()
        self.latency = LatencyMetrics()

        # Internal state for rolling window calculations
        self._nav_history: list[float] = []
        self._peak_nav: float = 0.0
        self._returns: list[float] = []

        # Latency tracking
        self._ack_latencies: list[float] = []
        self._fill_latencies: list[float] = []

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
            },
            "latency": {
                "avg_ack": self.latency.avg_ack_latency,
                "avg_fill": self.latency.avg_fill_latency,
                "last": self.latency.last_update_ms,
            },
            "timestamp": datetime.now().isoformat(),
        }
        return summary
