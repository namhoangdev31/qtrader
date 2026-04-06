"""PnL Attribution — Standash §8.2.

Decomposes total PnL into constituent sources:
- Alpha: Profit from signal accuracy
- Execution: Profit/loss from execution quality (slippage, timing)
- Fees: Cost of trading (maker/taker/funding)

Provides institutional transparency for performance reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PnLAttribution:
    """Single-trade PnL attribution breakdown."""

    symbol: str
    total_pnl: Decimal
    alpha_pnl: Decimal  # From signal accuracy
    execution_pnl: Decimal  # From execution quality (slippage)
    fee_pnl: Decimal  # Cost of fees (always negative or zero)
    timestamp: float = 0.0

    @property
    def attribution_pct(self) -> dict[str, float]:
        """Return attribution as percentages of total PnL."""
        total = abs(float(self.total_pnl))
        if total < 1e-10:
            return {"alpha": 0.0, "execution": 0.0, "fees": 0.0}
        return {
            "alpha": float(self.alpha_pnl) / total * 100,
            "execution": float(self.execution_pnl) / total * 100,
            "fees": float(self.fee_pnl) / total * 100,
        }


class PnLAttributionEngine:
    """PnL Attribution Engine — Standash §8.2.

    Decomposes portfolio PnL into:
    - Alpha PnL: (decision_price - fair_value) * quantity
    - Execution PnL: (decision_price - fill_price) * quantity
    - Fee PnL: -total_fees

    This enables performance attribution reporting:
    "X% of profit came from alpha, Y% from execution, Z% lost to fees."
    """

    def __init__(self) -> None:
        self._attributions: list[PnLAttribution] = []
        self._cumulative_alpha_pnl = Decimal("0")
        self._cumulative_execution_pnl = Decimal("0")
        self._cumulative_fee_pnl = Decimal("0")
        self._max_history = 100_000

    def attribute_trade(
        self,
        symbol: str,
        quantity: Decimal,
        decision_price: Decimal,
        fill_price: Decimal,
        fair_value: Decimal,
        total_fees: Decimal,
        timestamp: float = 0.0,
    ) -> PnLAttribution:
        """Attribute PnL for a single trade.

        Args:
            symbol: Trading symbol.
            quantity: Trade quantity (positive for buy, negative for sell).
            decision_price: Price at signal generation time.
            fill_price: Actual execution price.
            fair_value: Estimated fair value at decision time.
            total_fees: Total fees paid for the trade.
            timestamp: Trade timestamp.

        Returns:
            PnLAttribution with full breakdown.
        """
        side = Decimal("1") if quantity > 0 else Decimal("-1")
        abs_qty = abs(quantity)

        # Alpha PnL: profit from signal vs fair value
        alpha_pnl = side * (decision_price - fair_value) * abs_qty

        # Execution PnL: profit/loss from execution quality
        # Positive if filled better than decision price
        execution_pnl = side * (decision_price - fill_price) * abs_qty

        # Fee PnL: always negative (cost)
        fee_pnl = -total_fees

        # Total PnL
        total_pnl = alpha_pnl + execution_pnl + fee_pnl

        attribution = PnLAttribution(
            symbol=symbol,
            total_pnl=total_pnl,
            alpha_pnl=alpha_pnl,
            execution_pnl=execution_pnl,
            fee_pnl=fee_pnl,
            timestamp=timestamp,
        )

        # Update cumulative
        self._cumulative_alpha_pnl += alpha_pnl
        self._cumulative_execution_pnl += execution_pnl
        self._cumulative_fee_pnl += fee_pnl

        # Track history
        self._attributions.append(attribution)
        if len(self._attributions) > self._max_history:
            self._attributions = self._attributions[-self._max_history // 2 :]

        return attribution

    def get_cumulative_attribution(self) -> dict[str, Any]:
        """Return cumulative PnL attribution summary."""
        total = (
            self._cumulative_alpha_pnl + self._cumulative_execution_pnl + self._cumulative_fee_pnl
        )
        abs_total = abs(total)

        if abs_total < Decimal("1e-10"):
            pct = {"alpha": 0.0, "execution": 0.0, "fees": 0.0}
        else:
            pct = {
                "alpha": float(self._cumulative_alpha_pnl / abs_total * 100),
                "execution": float(self._cumulative_execution_pnl / abs_total * 100),
                "fees": float(self._cumulative_fee_pnl / abs_total * 100),
            }

        return {
            "total_pnl": float(total),
            "alpha_pnl": float(self._cumulative_alpha_pnl),
            "execution_pnl": float(self._cumulative_execution_pnl),
            "fee_pnl": float(self._cumulative_fee_pnl),
            "attribution_pct": pct,
            "trade_count": len(self._attributions),
        }

    def get_attribution_by_symbol(self) -> dict[str, dict[str, float]]:
        """Return PnL attribution broken down by symbol."""
        by_symbol: dict[str, dict[str, Decimal]] = {}
        for attr in self._attributions:
            if attr.symbol not in by_symbol:
                by_symbol[attr.symbol] = {
                    "total": Decimal("0"),
                    "alpha": Decimal("0"),
                    "execution": Decimal("0"),
                    "fees": Decimal("0"),
                }
            by_symbol[attr.symbol]["total"] += attr.total_pnl
            by_symbol[attr.symbol]["alpha"] += attr.alpha_pnl
            by_symbol[attr.symbol]["execution"] += attr.execution_pnl
            by_symbol[attr.symbol]["fees"] += attr.fee_pnl

        return {sym: {k: float(v) for k, v in vals.items()} for sym, vals in by_symbol.items()}
