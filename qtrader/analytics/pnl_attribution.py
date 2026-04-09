from __future__ import annotations
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PnLAttribution:
    symbol: str
    total_pnl: Decimal
    alpha_pnl: Decimal
    execution_pnl: Decimal
    fee_pnl: Decimal
    timestamp: float = 0.0

    @property
    def attribution_pct(self) -> dict[str, float]:
        total = abs(float(self.total_pnl))
        if total < 1e-10:
            return {"alpha": 0.0, "execution": 0.0, "fees": 0.0}
        return {
            "alpha": float(self.alpha_pnl) / total * 100,
            "execution": float(self.execution_pnl) / total * 100,
            "fees": float(self.fee_pnl) / total * 100,
        }


class PnLAttributionEngine:
    def __init__(self) -> None:
        self._attributions: list[PnLAttribution] = []
        self._cumulative_alpha_pnl = Decimal("0")
        self._cumulative_execution_pnl = Decimal("0")
        self._cumulative_fee_pnl = Decimal("0")
        self._max_history = 100000

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
        side = Decimal("1") if quantity > 0 else Decimal("-1")
        abs_qty = abs(quantity)
        alpha_pnl = side * (decision_price - fair_value) * abs_qty
        execution_pnl = side * (decision_price - fill_price) * abs_qty
        fee_pnl = -total_fees
        total_pnl = alpha_pnl + execution_pnl + fee_pnl
        attribution = PnLAttribution(
            symbol=symbol,
            total_pnl=total_pnl,
            alpha_pnl=alpha_pnl,
            execution_pnl=execution_pnl,
            fee_pnl=fee_pnl,
            timestamp=timestamp,
        )
        self._cumulative_alpha_pnl += alpha_pnl
        self._cumulative_execution_pnl += execution_pnl
        self._cumulative_fee_pnl += fee_pnl
        self._attributions.append(attribution)
        if len(self._attributions) > self._max_history:
            self._attributions = self._attributions[-self._max_history // 2 :]
        return attribution

    def get_cumulative_attribution(self) -> dict[str, Any]:
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
        return {sym: {k: float(v) for (k, v) in vals.items()} for (sym, vals) in by_symbol.items()}
