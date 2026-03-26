"""Capital accounting system for tracking NAV, fees, and P&L."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.oms.order_management_system import Position


@dataclass
class FeeEvent:
    """Fee event record."""

    timestamp: str  # ISO format timestamp
    exchange: str
    symbol: str
    fee_type: str  # maker, taker, funding, withdrawal, deposit
    amount: float  # Fee amount in USD
    metadata: dict[str, Any] | None = None


@dataclass
class CapitalLedger:
    """
    Capital ledger for tracking portfolio value, fees, and P&L.

    Tracks:
    - Cash balance (multi-currency converted to USD)
    - Position values (mark-to-market)
    - Fees paid
    - Funding rates received/paid
    - Historical NAV for P&L calculation
    """

    def __init__(self) -> None:
        """Initialize the capital ledger."""
        # Cash balances by currency (all converted to USD equivalent)
        self.cash_balances: dict[str, float] = defaultdict(float)
        # USD equivalent of total cash
        self.total_cash_usd: float = 0.0

        # Fee tracking
        self.fees_paid: list[FeeEvent] = []
        self.total_fees_paid: float = 0.0

        # Funding rate tracking
        self.funding_payments: list[dict[str, Any]] = []  # {timestamp, symbol, rate, amount}
        self.total_funding_paid: float = 0.0

        # Historical NAV tracking for P&L calculation
        self.nav_history: list[dict[str, Any]] = []  # [{timestamp, nav, cash, position_value}]
        self.current_nav: float = 0.0
        self.previous_nav: float = 0.0

        # Exchange rate cache (in production, would come from a feed)
        self.exchange_rates: dict[str, float] = {"USD": 1.0}  # currency -> USD rate

    def set_exchange_rate(self, currency: str, rate_to_usd: float) -> None:
        """
        Set exchange rate for currency to USD conversion.

        Args:
            currency: Currency code (e.g., 'EUR', 'BTC')
            rate_to_usd: Exchange rate (1 unit of currency = rate_to_usd USD)
        """
        self.exchange_rates[currency] = rate_to_usd
        # Recalculate total cash if we have balances in this currency
        if currency in self.cash_balances:
            self._update_total_cash()

    def record_cash_deposit(self, amount: float, currency: str = "USD") -> None:
        """
        Record a cash deposit.

        Args:
            amount: Amount deposited
            currency: Currency of deposit (default USD)
        """
        self.cash_balances[currency] += amount
        self._update_total_cash()
        self._record_nav_snapshot()

    def record_cash_withdrawal(self, amount: float, currency: str = "USD") -> None:
        """
        Record a cash withdrawal.

        Args:
            amount: Amount withdrawn
            currency: Currency of withdrawal (default USD)
        """
        if self.cash_balances[currency] < amount:
            raise ValueError(
                f"Insufficient {currency} balance: {self.cash_balances[currency]} < {amount}"
            )

        self.cash_balances[currency] -= amount
        self._update_total_cash()
        self._record_nav_snapshot()

    def record_fee(
        self, exchange: str, symbol: str, fee: float, timestamp: str, fee_type: str = "taker"
    ) -> None:
        """
        Record a fee payment.

        Args:
            exchange: Exchange where fee was incurred
            symbol: Trading symbol
            fee: Fee amount (in USD)
            timestamp: ISO format timestamp
            fee_type: Type of fee (maker, taker, funding, etc.)
        """
        fee_event = FeeEvent(
            timestamp=timestamp,
            exchange=exchange,
            symbol=symbol,
            fee_type=fee_type,
            amount=fee,
            metadata=None,
        )
        self.fees_paid.append(fee_event)
        self.total_fees_paid += fee
        self._record_nav_snapshot()

    def record_funding_rate(
        self, symbol: str, rate: float, timestamp: str, position_size: float
    ) -> None:
        """
        Record funding rate payment/receipt.

        Args:
            symbol: Trading symbol
            rate: Funding rate (e.g., 0.0001 for 0.01%)
            timestamp: ISO format timestamp
            position_size: Position size in base currency (positive=long, negative=short)
        """
        # Funding payment = position_size * mark_price * rate
        # For simplicity, we'll assume mark_price is tracked elsewhere and passed in
        # In practice, this would use the current mark price
        funding_amount = position_size * rate  # Simplified

        self.funding_payments.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "rate": rate,
                "position_size": position_size,
                "amount": funding_amount,
            }
        )

        if funding_amount > 0:
            self.total_funding_paid += funding_amount  # Positive = we paid
            self.record_fee("funding", symbol, funding_amount, timestamp, "funding")
        else:
            self.total_funding_paid += funding_amount  # Negative = we received
            # Negative fees represent rebates

    def _update_total_cash(self) -> None:
        """Update total cash USD equivalent from all currency balances."""
        total = 0.0
        for currency, amount in self.cash_balances.items():
            rate = self.exchange_rates.get(currency, 0.0)
            total += amount * rate
        self.total_cash_usd = total

    def _record_nav_snapshot(self) -> None:
        """Record a snapshot of current NAV for historical tracking."""
        # This would be called periodically or after significant events
        # In practice, the calling code would provide position and price data
        pass

    def calculate_nav(self, positions: dict[str, Position], prices: dict[str, float]) -> float:
        """
        Calculate Net Asset Value (NAV).

        Args:
            positions: Dictionary of symbol -> Position
            prices: Dictionary of symbol -> current price

        Returns:
            NAV as float (USD equivalent)
        """
        # Calculate position market value
        position_value = 0.0
        for symbol, position in positions.items():
            if symbol in prices:
                # Position value = quantity * price
                position_value += position.qty * prices[symbol]

        # NAV = Cash + Position Value
        nav = self.total_cash_usd + position_value

        # Update historical tracking
        self.previous_nav = self.current_nav
        self.current_nav = nav

        # Record snapshot (in production, would do this with timestamp)
        self.nav_history.append(
            {"nav": nav, "cash": self.total_cash_usd, "position_value": position_value}
        )

        return nav

    def calculate_daily_pnl(self) -> float:
        """
        Calculate daily P&L as change in NAV.

        Returns:
            Daily P&L as float
        """
        return self.current_nav - self.previous_nav

    def get_total_fees(
        self, start_timestamp: str | None = None, end_timestamp: str | None = None
    ) -> float:
        """
        Get total fees paid in a time period.

        Args:
            start_timestamp: Start time in ISO format (inclusive)
            end_timestamp: End time in ISO format (inclusive)

        Returns:
            Total fees paid in period
        """
        if start_timestamp is None and end_timestamp is None:
            return self.total_fees_paid

        total = 0.0
        for fee in self.fees_paid:
            if start_timestamp and fee.timestamp < start_timestamp:
                continue
            if end_timestamp and fee.timestamp > end_timestamp:
                continue
            total += fee.amount
        return total

    def get_nav_components(
        self, positions: dict[str, Position], prices: dict[str, float]
    ) -> dict[str, float]:
        """
        Get detailed NAV components.

        Args:
            positions: Dictionary of symbol -> Position
            prices: Dictionary of symbol -> current price

        Returns:
            Dictionary with NAV components
        """
        position_value = 0.0
        for symbol, position in positions.items():
            if symbol in prices:
                position_value += position.qty * prices[symbol]

        return {
            "cash": self.total_cash_usd,
            "position_value": position_value,
            "nav": self.total_cash_usd + position_value,
            "fees_paid": self.total_fees_paid,
            "funding_paid": self.total_funding_paid,
        }
