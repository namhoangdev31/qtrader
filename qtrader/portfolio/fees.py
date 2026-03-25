"""Real-time fee tracking for trading activities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import defaultdict
import time


@dataclass
class FeeSnapshot:
    """Snapshot of fees at a point in time."""

    timestamp: float
    maker_fees: float
    taker_fees: float
    funding_fees: float
    withdrawal_fees: float
    deposit_fees: float
    total_fees: float


@dataclass
class FeeTracker:
    """
    Real-time fee tracker for trading activities.

    Tracks fees from trades and funding in real-time for immediate P&L calculation.
    """

    def __init__(self) -> None:
        """Initialize the fee tracker."""
        # Fee accumulators by type
        self.maker_fees: float = 0.0
        self.taker_fees: float = 0.0
        self.funding_fees: float = 0.0
        self.withdrawal_fees: float = 0.0
        self.deposit_fees: float = 0.0

        # Total fees
        self.total_fees: float = 0.0

        # Historical snapshots for tracking fee accrual over time
        self.fee_history: List[FeeSnapshot] = []

        # Per-symbol fee tracking (useful for attribution)
        self.symbol_fees: Dict[str, float] = defaultdict(float)

        # Per-exchange fee tracking
        self.exchange_fees: Dict[str, float] = defaultdict(float)

    def record_trade_fee(
        self,
        price: float,
        quantity: float,
        fee_rate: float,
        fee_type: str = "taker",
        symbol: str = "",
        exchange: str = "",
        timestamp: Optional[float] = None,
    ) -> float:
        """
        Record a trading fee.

        Args:
            price: Trade price
            quantity: Trade quantity (absolute value)
            fee_rate: Fee rate (e.g., 0.001 for 0.1%)
            fee_type: Type of fee ("maker" or "taker")
            symbol: Trading symbol (optional, for attribution)
            exchange: Exchange name (optional, for attribution)
            timestamp: Unix timestamp (defaults to current time)

        Returns:
            Fee amount charged
        """
        if timestamp is None:
            timestamp = time.time()

        # Calculate fee: price × quantity × fee_rate
        fee_amount = abs(price) * abs(quantity) * fee_rate

        # Accumulate by type
        if fee_type.lower() == "maker":
            self.maker_fees += fee_amount
        elif fee_type.lower() == "taker":
            self.taker_fees += fee_amount
        elif fee_type.lower() == "funding":
            self.funding_fees += fee_amount
        elif fee_type.lower() == "withdrawal":
            self.withdrawal_fees += fee_amount
        elif fee_type.lower() == "deposit":
            self.deposit_fees += fee_amount
        else:
            # Default to taker for unknown types
            self.taker_fees += fee_amount

        # Update total
        self.total_fees += fee_amount

        # Track by symbol and exchange if provided
        if symbol:
            self.symbol_fees[symbol] += fee_amount
        if exchange:
            self.exchange_fees[exchange] += fee_amount

        # Record snapshot
        self._record_snapshot(timestamp)

        return fee_amount

    def record_funding_fee(
        self,
        position_size: float,
        funding_rate: float,
        mark_price: float,
        symbol: str = "",
        exchange: str = "",
        timestamp: Optional[float] = None,
    ) -> float:
        """
        Record a funding fee.

        Args:
            position_size: Position size (positive=long, negative=short)
            funding_rate: Funding rate (e.g., 0.0001 for 0.01%)
            mark_price: Current mark price of the asset
            symbol: Trading symbol (optional)
            exchange: Exchange name (optional)
            timestamp: Unix timestamp (defaults to current time)

        Returns:
            Funding fee amount (positive=paid, negative=received)
        """
        if timestamp is None:
            timestamp = time.time()

        # Calculate funding: position × mark_price × funding_rate
        # Positive means we pay funding, negative means we receive funding
        funding_amount = position_size * mark_price * funding_rate

        # Accumulate as funding fee
        self.funding_fees += funding_amount
        self.total_fees += funding_amount

        # Track by symbol and exchange if provided
        if symbol:
            self.symbol_fees[symbol] += funding_amount
        if exchange:
            self.exchange_fees[exchange] += funding_amount

        # Record snapshot
        self._record_snapshot(timestamp)

        return funding_amount

    def _record_snapshot(self, timestamp: float) -> None:
        """Record a fee snapshot."""
        snapshot = FeeSnapshot(
            timestamp=timestamp,
            maker_fees=self.maker_fees,
            taker_fees=self.taker_fees,
            funding_fees=self.funding_fees,
            withdrawal_fees=self.withdrawal_fees,
            deposit_fees=self.deposit_fees,
            total_fees=self.total_fees,
        )
        self.fee_history.append(snapshot)

    def get_fee_summary(self) -> Dict[str, float]:
        """
        Get summary of all fees.

        Returns:
            Dictionary with fee breakdown
        """
        return {
            "maker_fees": self.maker_fees,
            "taker_fees": self.taker_fees,
            "funding_fees": self.funding_fees,
            "withdrawal_fees": self.withdrawal_fees,
            "deposit_fees": self.deposit_fees,
            "total_fees": self.total_fees,
        }

    def get_symbol_fees(self, symbol: Optional[str] = None) -> Dict[str, float]:
        """
        Get fees by symbol.

        Args:
            symbol: Specific symbol to get fees for (None for all)

        Returns:
            Dictionary of symbol -> fee amount
        """
        if symbol is None:
            return dict(self.symbol_fees)
        return {symbol: self.symbol_fees.get(symbol, 0.0)}

    def get_exchange_fees(self, exchange: Optional[str] = None) -> Dict[str, float]:
        """
        Get fees by exchange.

        Args:
            exchange: Specific exchange to get fees for (None for all)

        Returns:
            Dictionary of exchange -> fee amount
        """
        if exchange is None:
            return dict(self.exchange_fees)
        return {exchange: self.exchange_fees.get(exchange, 0.0)}

    def get_recent_fees(self, since_timestamp: float) -> List[FeeSnapshot]:
        """
        Get fee snapshots since a timestamp.

        Args:
            since_timestamp: Unix timestamp to get snapshots since

        Returns:
            List of fee snapshots
        """
        return [snapshot for snapshot in self.fee_history if snapshot.timestamp >= since_timestamp]

    def reset(self) -> None:
        """Reset all fee tracking."""
        # Manually reset all attributes to initial state
        self.maker_fees = 0.0
        self.taker_fees = 0.0
        self.funding_fees = 0.0
        self.withdrawal_fees = 0.0
        self.deposit_fees = 0.0
        self.total_fees = 0.0
        self.fee_history.clear()
        self.symbol_fees.clear()
        self.exchange_fees.clear()
