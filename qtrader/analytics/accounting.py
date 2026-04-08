from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.analytics.accounting")


class FundAccountingEngine:
    r"""
    Principal Fund Accounting System.

    Objective: Continuously track portfolio value, unrealized PnL, and NAV to
    ensure bit-perfect financial state visibility and regulatory auditability.

    Model: Mark-to-Market (MtM) Valuation ($PnL = \sum (P_c - P_e) \cdot Qty$).
    Constraint: Total Transparency ($NAV = Assets - Liabilities$).
    """

    def __init__(self) -> None:
        """
        Initialize the institutional accounting engine.
        """
        # Telemetry for institutional situational awareness.
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
        r"""
        Produce a terminal financial report and compute the Net Asset Value (NAV).

        Forensic Logic:
        1. Unrealized PnL Aggregation: $\sum (MarketPrice - EntryPrice) \cdot Qty$.
        2. Asset Valuation: $Cash + EntryValue + PnL$.
        3. Net Asset Valuation: $TotalAssets - Liabilities$.
        4. Performance Metric: Returns computed as $(NAV_t - NAV_{t-1}) / NAV_{t-1}$.
        """
        valuation_start = time.time()

        # 1. Metrological PnL and Exposure Calculation.
        unrealized_pnl = 0.0
        total_entry_value = 0.0

        for pos in positions:
            symbol = str(pos.get("symbol", "UNKNOWN"))
            entry_price = float(pos.get("entry_price", 0.0))
            quantity = float(pos.get("quantity", 0.0))

            # Fetch live market price or fallback to entry price for structural safety.
            current_price = market_prices.get(symbol, entry_price)

            # Mark-to-Market differential.
            unrealized_pnl += (current_price - entry_price) * quantity
            total_entry_value += entry_price * abs(quantity)

        # 2. Balance Sheet Lifecycle.
        total_assets = cash_balance + total_entry_value + unrealized_pnl
        net_asset_value = total_assets - liabilities

        # 3. Performance Metrology.
        pnl_return = 0.0
        if previous_nav and previous_nav > 0:
            pnl_return = (net_asset_value - previous_nav) / previous_nav

        # 4. Telemetry Indexing.
        self._valuation_cycle_count += 1
        self._peak_nav_historical = max(self._peak_nav_historical, net_asset_value)
        self._last_calculated_pnl = unrealized_pnl

        _LOG.info(
            f"[ACCOUNTING] STATE_INDEXED | NAV: {net_asset_value:,.2f} "
            f"| PnL: {unrealized_pnl:,.2f} | Cycles: {self._valuation_cycle_count}"
        )

        # 5. Certification Artifact Construction.
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
        """
        situational awareness for institutional financial veracity.
        """
        return {
            "status": "FINANCIAL_GOVERNANCE",
            "peak_nav_historical": round(self._peak_nav_historical, 4),
            "unrealized_pnl_snapshot": round(self._last_calculated_pnl, 4),
            "total_valuation_cycles": self._valuation_cycle_count,
        }
