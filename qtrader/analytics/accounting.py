from __future__ import annotations
import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.analytics.accounting")


class FundAccountingEngine:
    def __init__(self) -> None:
        self._peak_nav_historical: float = 0.0
        self._last_calculated_pnl: float = 0.0
        self._valuation_cycle_count: int = 0

    def update_financial_state(
        self,
        positions: list[dict[str, Any]],
        market_prices: dict[str, float],
        cash_balance: float = 0.0,
        liabilities: float = 0.0,
        previous_nav: float | None = None,
    ) -> dict[str, Any]:
        valuation_start = time.time()
        unrealized_pnl = 0.0
        total_entry_value = 0.0
        for pos in positions:
            symbol = str(pos.get("symbol", "UNKNOWN"))
            entry_price = float(pos.get("entry_price", 0.0))
            quantity = float(pos.get("quantity", 0.0))
            current_price = market_prices.get(symbol, entry_price)
            unrealized_pnl += (current_price - entry_price) * quantity
            total_entry_value += entry_price * abs(quantity)
        total_assets = cash_balance + total_entry_value + unrealized_pnl
        net_asset_value = total_assets - liabilities
        pnl_return = 0.0
        if previous_nav and previous_nav > 0:
            pnl_return = (net_asset_value - previous_nav) / previous_nav
        self._valuation_cycle_count += 1
        self._peak_nav_historical = max(self._peak_nav_historical, net_asset_value)
        self._last_calculated_pnl = unrealized_pnl
        _LOG.info(
            f"[ACCOUNTING] STATE_INDEXED | NAV: {net_asset_value:,.2f} | PnL: {unrealized_pnl:,.2f} | Cycles: {self._valuation_cycle_count}"
        )
        artifact = {
            "status": "VALUATION_FINALIZED",
            "finances": {
                "net_asset_value": round(net_asset_value, 4),
                "unrealized_pnl": round(unrealized_pnl, 4),
                "liabilities_total": round(liabilities, 4),
            },
            "performance": {
                "valuation_return": round(pnl_return, 6),
                "total_equity_base": round(total_assets, 4),
            },
            "certification": {
                "peak_nav_historical": round(self._peak_nav_historical, 4),
                "timestamp": time.time(),
                "valuation_latency_ms": round((time.time() - valuation_start) * 1000, 4),
            },
        }
        return artifact

    def get_accounting_telemetry(self) -> dict[str, Any]:
        return {
            "status": "FINANCIAL_GOVERNANCE",
            "peak_nav_historical": round(self._peak_nav_historical, 4),
            "unrealized_pnl_snapshot": round(self._last_calculated_pnl, 4),
            "total_valuation_cycles": self._valuation_cycle_count,
        }
