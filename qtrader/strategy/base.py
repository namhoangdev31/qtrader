from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

import polars as pl

from qtrader.core.event import FillEvent, OrderEvent, SignalEvent

__all__ = ["Strategy", "BaseStrategy"]

_LOG = logging.getLogger("qtrader.strategy.base")


@runtime_checkable
class Strategy(Protocol):
    """Protocol for converting signals into orders."""

    def on_signal(self, event: SignalEvent) -> list[OrderEvent]:  # pragma: no cover - interface
        """Handle an incoming signal and return zero or more orders."""


@dataclass(slots=True)
class BaseStrategy:
    """Base class for strategies with common accounting and utilities.

    Attributes:
        symbol: Primary trading symbol for this strategy.
        capital: Notional capital allocated to the strategy.
        fills_log: Polars DataFrame of historical fills with columns:
            symbol, side, qty, price, pnl, timestamp.
    """

    symbol: str
    capital: float = 100_000.0
    _position: dict[str, float] = field(default_factory=dict, init=False)
    fills_log: pl.DataFrame = field(
        default_factory=lambda: pl.DataFrame(
            {
                "symbol": pl.Series([], dtype=pl.String),
                "side": pl.Series([], dtype=pl.String),
                "qty": pl.Series([], dtype=pl.Float64),
                "price": pl.Series([], dtype=pl.Float64),
                "pnl": pl.Series([], dtype=pl.Float64),
                "timestamp": pl.Series([], dtype=pl.Datetime(time_unit="us")),
            },
        ),
        init=False,
    )

    def on_signal(self, event: SignalEvent) -> list[OrderEvent]:
        """Convert a signal into one or more orders.

        Subclasses are expected to override this method.

        Args:
            event: Incoming `SignalEvent`.

        Returns:
            List of `OrderEvent` objects to be submitted.
        """
        raise NotImplementedError("BaseStrategy.on_signal must be implemented by subclasses.")

    def on_fill(self, event: FillEvent) -> None:
        """Update internal position tracking and fill log on each fill.

        Args:
            event: Executed `FillEvent` for an order.
        """
        qty_signed = event.quantity if event.side.upper() == "BUY" else -event.quantity
        prev_qty = self._position.get(event.symbol, 0.0)
        self._position[event.symbol] = prev_qty + qty_signed

        pnl = 0.0
        ts: datetime = event.timestamp
        new_row = pl.DataFrame(
            {
                "symbol": [event.symbol],
                "side": [event.side],
                "qty": [float(event.quantity)],
                "price": [float(event.price)],
                "pnl": [pnl],
                "timestamp": [ts],
            },
        )
        self.fills_log = pl.concat([self.fills_log, new_row], how="vertical")
        _LOG.debug("Recorded fill for %s qty=%s side=%s", event.symbol, event.quantity, event.side)

    def get_position(self, symbol: str) -> float:
        """Return current net quantity for a symbol.

        Args:
            symbol: Instrument identifier.

        Returns:
            Net position quantity (positive=long, negative=short).
        """
        return float(self._position.get(symbol, 0.0))

    def expected_value(self) -> dict[str, float]:
        """Compute per-asset expected value from historical fills.

        Per-asset EV is defined as:

        \\[
        EV = win\\_rate \\cdot avg\\_win - (1 - win\\_rate) \\cdot avg\\_loss
        \\]

        Requires at least 10 fills overall; returns an empty dict otherwise.

        Returns:
            Mapping from symbol to expected value estimate.
        """
        if self.fills_log.height < 10:
            return {}

        df = self.fills_log
        wins = df.filter(pl.col("pnl") > 0.0)
        losses = df.filter(pl.col("pnl") < 0.0)

        total_counts = df.group_by("symbol").len().rename({"len": "total"})
        win_counts = wins.group_by("symbol").len().rename({"len": "wins"}) if wins.height > 0 else pl.DataFrame(
            {"symbol": pl.Series([], dtype=pl.String), "wins": pl.Series([], dtype=pl.UInt32)},
        )
        avg_win = wins.group_by("symbol").agg(pl.col("pnl").mean().alias("avg_win")) if wins.height > 0 else pl.DataFrame(
            {"symbol": pl.Series([], dtype=pl.String), "avg_win": pl.Series([], dtype=pl.Float64)},
        )
        avg_loss = losses.group_by("symbol").agg(pl.col("pnl").mean().alias("avg_loss")) if losses.height > 0 else pl.DataFrame(
            {"symbol": pl.Series([], dtype=pl.String), "avg_loss": pl.Series([], dtype=pl.Float64)},
        )

        joined = (
            total_counts.join(win_counts, on="symbol", how="left")
            .join(avg_win, on="symbol", how="left")
            .join(avg_loss, on="symbol", how="left")
            .with_columns(
                pl.col("wins").fill_null(0),
                pl.col("avg_win").fill_null(0.0),
                pl.col("avg_loss").fill_null(0.0).abs(),
            )
        )

        joined = joined.with_columns(
            (pl.col("wins") / pl.col("total")).alias("win_rate"),
        )

        joined = joined.with_columns(
            (
                pl.col("win_rate") * pl.col("avg_win")
                - (1.0 - pl.col("win_rate")) * pl.col("avg_loss")
            ).alias("ev"),
        )

        return {
            row["symbol"]: float(row["ev"])
            for row in joined.select("symbol", "ev").to_dicts()
        }

    def win_rate_trailing(self, n: int = 100) -> float:
        """Fraction of profitable trades in the last ``n`` fills.

        Args:
            n: Maximum number of most recent fills to consider.

        Returns:
            Trailing win rate in [0, 1]. Returns 0.0 if there are no fills.
        """
        if self.fills_log.height == 0:
            return 0.0
        df = self.fills_log.tail(n)
        if df.height == 0:
            return 0.0
        wins = df.filter(pl.col("pnl") > 0.0).height
        return float(wins) / float(df.height)

    def create_order(
        self,
        quantity: float,
        side: str,
        order_type: str = "MARKET",
        price: float | None = None,
    ) -> OrderEvent:
        """Helper to create a basic `OrderEvent`.

        Args:
            quantity: Order quantity.
            side: \"BUY\" or \"SELL\".
            order_type: Order type string, default \"MARKET\".
            price: Optional limit price.

        Returns:
            Constructed `OrderEvent` instance.
        """
        return OrderEvent(
            symbol=self.symbol,
            order_type=order_type,
            quantity=quantity,
            price=price,
            side=side,
        )


"""
Pytest-style examples (conceptual):

def test_on_fill_updates_position() -> None:
    from qtrader.core.event import FillEvent, EventType

    strat = BaseStrategy(symbol="AAPL")
    fill = FillEvent(
        type=EventType.FILL,
        symbol="AAPL",
        quantity=10.0,
        price=150.0,
        commission=0.0,
        side="BUY",
        order_id="1",
        fill_id="1",
    )
    strat.on_fill(fill)
    assert strat.get_position("AAPL") == 10.0


def test_win_rate_trailing_no_fills() -> None:
    strat = BaseStrategy(symbol="AAPL")
    assert strat.win_rate_trailing() == 0.0
"""

