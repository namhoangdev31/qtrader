from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from qtrader.core.decimal_adapter import d, math_authority


class FinancialEngine:
    """
    Sovereign Authority for Financial Computations.
    Standardizes on exact formulas for metrics across Backtest and Live modes.
    Ensures ε=0 during intermediate financial accumulation.
    """

    @staticmethod
    def pnl(entry_price: Decimal, exit_price: Decimal, quantity: Decimal) -> Decimal:
        """
        Exact Realized PnL Formula: (Exit - Entry) * Quantity.
        Normalized to 18dp intermediate precision.
        """
        math_authority.verify_no_float(entry_price, exit_price, quantity)
        return (exit_price - entry_price) * quantity

    @staticmethod
    def nav(cash: Decimal, positions: Mapping[str, Mapping[str, Decimal]]) -> Decimal:
        """
        Canonical NAV Formula: Total Equity = Cash + sum(Qty_i * Price_i).
        Note: positions format: {"BTC": {"qty": D, "market_price": D}}
        """
        math_authority.verify_no_float(cash)
        total_equity = cash
        
        for symbol, data in positions.items():
            qty = data.get("qty", d(0))
            price = data.get("market_price", d(0))
            math_authority.verify_no_float(qty, price)
            total_equity += qty * price
            
        return total_equity

    @staticmethod
    def fee(notional: Decimal, fee_rate_bps: Decimal) -> Decimal:
        """
        Standard Fee Formula: Notional * FeeRate(bps) / 10000.
        """
        math_authority.verify_no_float(notional, fee_rate_bps)
        # 1 basis point = 0.0001
        multiplier = fee_rate_bps / d(10000)
        return notional * multiplier

    @staticmethod
    def slippage(execution_price: Decimal, reference_price: Decimal, quantity: Decimal) -> Decimal:
        """
        Absolute Slippage Formula: (ExecPrice - RefPrice) * Quantity.
        Positive value indicates adverse slippage (execution worse than reference).
        """
        math_authority.verify_no_float(execution_price, reference_price, quantity)
        return (execution_price - reference_price) * quantity

    @staticmethod
    def slippage_bps(execution_price: Decimal, reference_price: Decimal) -> Decimal:
        """
        Relative Slippage (basis points): |(ExecPrice - RefPrice) / RefPrice| * 10000.
        """
        math_authority.verify_no_float(execution_price, reference_price)
        if reference_price == 0:
            return d(0)
            
        ratio = (execution_price - reference_price) / reference_price
        return ratio * d(10000)


# Module-level singleton
financial_authority = FinancialEngine()
