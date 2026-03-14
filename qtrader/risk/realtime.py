from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import polars as pl

from qtrader.core.bus import EventBus
from qtrader.core.event import RiskEvent
from qtrader.risk.limits import PortfolioState, RiskLimit

__all__ = ["RealTimeRiskEngine"]

_LOG = logging.getLogger("qtrader.risk.realtime")


@dataclass(slots=True)
class RealTimeRiskEngine:
    """Real-time portfolio risk monitor.

    Tracks positions, PnL history and derived risk measures. Limit checks are
    pure computations; asynchronous publication of `RiskEvent` instances to the
    `EventBus` is handled via :meth:`publish_breaches`.

    Attributes:
        positions: Positions DataFrame with columns
            ``symbol``, ``qty``, ``price``, ``market_value``, ``weight``.
        pnl_history: Series of trailing daily PnL values (most recent last).
        equity: Current portfolio equity.
        hwm: High-water mark of portfolio equity.
        current_drawdown: Current drawdown from the high-water mark.
    """

    limits: Sequence[RiskLimit] = field(default_factory=tuple)
    event_bus: EventBus | None = None
    positions: pl.DataFrame = field(
        default_factory=lambda: pl.DataFrame(
            {
                "symbol": pl.Series([], dtype=pl.String),
                "qty": pl.Series([], dtype=pl.Float64),
                "price": pl.Series([], dtype=pl.Float64),
                "market_value": pl.Series([], dtype=pl.Float64),
                "weight": pl.Series([], dtype=pl.Float64),
            },
        ),
    )
    pnl_history: pl.Series = field(
        default_factory=lambda: pl.Series(name="daily_pnl", values=[], dtype=pl.Float64),
    )
    equity: float = 0.0
    hwm: float = 0.0
    current_drawdown: float = 0.0
    _max_history: int = 252

    # ------------------------------------------------------------------ #
    # State update methods                                               #
    # ------------------------------------------------------------------ #

    def update_position(self, symbol: str, qty: float, price: float) -> None:
        """Insert or update a single position.

        Args:
            symbol: Instrument identifier.
            qty: Position quantity (signed).
            price: Latest traded or mark price.
        """
        mv = qty * price
        if self.positions.height == 0:
            df = pl.DataFrame(
                {
                    "symbol": [symbol],
                    "qty": [qty],
                    "price": [price],
                    "market_value": [mv],
                },
            )
        else:
            df = self.positions.clone()
            if symbol in df.get_column("symbol").to_list():
                df = df.with_columns(
                    pl.when(pl.col("symbol") == symbol)
                    .then(pl.lit(qty))
                    .otherwise(pl.col("qty"))
                    .alias("qty"),
                    pl.when(pl.col("symbol") == symbol)
                    .then(pl.lit(price))
                    .otherwise(pl.col("price"))
                    .alias("price"),
                )
                df = df.with_columns((pl.col("qty") * pl.col("price")).alias("market_value"))
            else:
                new_row = pl.DataFrame(
                    {
                        "symbol": [symbol],
                        "qty": [qty],
                        "price": [price],
                        "market_value": [mv],
                    },
                )
                df = pl.concat((df, new_row), how="vertical")

        total_abs_mv = float(df.get_column("market_value").abs().sum())
        if total_abs_mv > 0.0:
            df = df.with_columns((pl.col("market_value").abs() / total_abs_mv).alias("weight"))
        else:
            df = df.with_columns(pl.lit(0.0).alias("weight"))

        self.positions = df
        self.equity = float(self.positions.get_column("market_value").sum())
        if self.equity > self.hwm:
            self.hwm = self.equity
        self.current_drawdown = self._compute_drawdown()

    def update_pnl(self, pnl_delta: float) -> None:
        """Append a new daily PnL observation and maintain rolling history.

        Args:
            pnl_delta: Realised or marked-to-market PnL for the day.
        """
        if self.pnl_history.len() == 0:
            series = pl.Series(name="daily_pnl", values=[pnl_delta], dtype=pl.Float64)
        else:
            series = pl.concat(
                [self.pnl_history, pl.Series(name="daily_pnl", values=[pnl_delta])],
                how="vertical",
            )
        if series.len() > self._max_history:
            series = series.tail(self._max_history)
        self.pnl_history = series

    # ------------------------------------------------------------------ #
    # Risk metrics                                                       #
    # ------------------------------------------------------------------ #

    def compute_var(self, confidence: float = 0.95, horizon_days: int = 1) -> float:
        """Compute historical-simulation Value-at-Risk.

        Args:
            confidence: Confidence level (e.g. 0.95).
            horizon_days: VaR horizon in days.

        Returns:
            Positive VaR amount in portfolio currency.
        """
        if self.pnl_history.len() == 0 or self.equity <= 0.0:
            return 0.0
        losses = (-self.pnl_history).to_frame("loss")
        alpha = 1.0 - confidence
        # Quantile of loss distribution (left tail).
        var_loss = float(losses.select(pl.col("loss").quantile(alpha, interpolation="nearest")).item())
        if var_loss <= 0.0:
            return 0.0
        scaled = var_loss * (horizon_days**0.5)
        return float(scaled)

    def compute_cvar(self, confidence: float = 0.95) -> float:
        """Compute Conditional Value-at-Risk (Expected Shortfall).

        Args:
            confidence: Confidence level (e.g. 0.95).

        Returns:
            Positive CVaR amount in portfolio currency.
        """
        if self.pnl_history.len() == 0 or self.equity <= 0.0:
            return 0.0
        var_value = self.compute_var(confidence=confidence, horizon_days=1)
        if var_value <= 0.0:
            return 0.0
        losses = (-self.pnl_history).to_frame("loss")
        tail = losses.filter(pl.col("loss") >= var_value)
        if tail.height == 0:
            return 0.0
        cvar_loss = float(tail.select(pl.col("loss").mean()).item())
        return float(cvar_loss)

    def compute_hhi(self) -> float:
        """Compute Herfindahl-Hirschman Index of position concentration."""
        if self.positions.height == 0:
            return 0.0
        weights = self.positions.get_column("weight")
        hhi_value = float((weights**2).sum())
        return hhi_value

    # ------------------------------------------------------------------ #
    # Limits & EventBus integration                                     #
    # ------------------------------------------------------------------ #

    def _build_portfolio_state(self) -> PortfolioState:
        """Construct a `PortfolioState` from the current engine state."""
        daily_pnl = float(self.pnl_history.tail(1).item()) if self.pnl_history.len() > 0 else 0.0
        var_95 = self.compute_var(confidence=0.95, horizon_days=1)
        hhi = self.compute_hhi()
        return PortfolioState(
            equity=self.equity,
            hwm=self.hwm,
            positions=self.positions,
            daily_pnl=daily_pnl,
            var_95=var_95,
            hhi=hhi,
        )

    def check_all_limits(self) -> list[RiskEvent]:
        """Evaluate all configured limits and return any breaches.

        Returns:
            List of `RiskEvent` objects; empty list means all limits are satisfied.
        """
        if not self.limits:
            return []
        state = self._build_portfolio_state()
        breaches: list[RiskEvent] = []
        for limit in self.limits:
            event = limit.check(state)
            if event is not None:
                breaches.append(event)
        return breaches

    async def publish_breaches(self) -> list[RiskEvent]:
        """Publish any breached limits as `RiskEvent`s to the event bus.

        Returns:
            The list of breached `RiskEvent`s.
        """
        breaches = self.check_all_limits()
        if self.event_bus is None or not breaches:
            return breaches

        for event in breaches:
            await self.event_bus.publish(event)
        _LOG.debug("Published %d risk breaches", len(breaches))
        return breaches

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _compute_drawdown(self) -> float:
        """Compute current drawdown as a fraction of HWM."""
        if self.hwm <= 0.0:
            return 0.0
        return (self.hwm - self.equity) / self.hwm


# ---------------------------------------------------------------------------
# Minimal inline tests (for documentation only)
# ---------------------------------------------------------------------------

"""
Pytest-style examples (conceptual):

def test_compute_hhi_single_position() -> None:
    engine = RealTimeRiskEngine()
    engine.update_position("AAPL", qty=100.0, price=150.0)
    hhi = engine.compute_hhi()
    assert hhi == pytest.approx(1.0)


def test_var_and_cvar_non_negative() -> None:
    engine = RealTimeRiskEngine()
    for pnl in (-100.0, 50.0, -20.0, 10.0):
        engine.update_pnl(pnl)
    var_95 = engine.compute_var()
    cvar_95 = engine.compute_cvar()
    assert var_95 >= 0.0
    assert cvar_95 >= 0.0


async def test_publish_breaches_uses_event_bus(event_bus: EventBus) -> None:
    engine = RealTimeRiskEngine(limits=[], event_bus=event_bus)
    events = await engine.publish_breaches()
    assert events == []
"""

