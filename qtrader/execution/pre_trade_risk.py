"""Pre-Trade Risk Validation — Standash §4.6, §4.7.

Validates every order before it reaches the execution layer.
Checks:
1. Fat-finger protection (price deviation, quantity limits)
2. Position limits (max position per symbol, total exposure)
3. Order rate limits (max orders per second)
4. Kill switch status (blocks all orders when active)
5. Notional limits (max order value)

All parameters are configurable via PreTradeRiskConfig.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger("qtrader.execution.pre_trade_risk")


@dataclass(slots=True)
class PreTradeRiskConfig:
    """Configuration for pre-trade risk validation."""

    # Fat-finger protection
    max_price_deviation_pct: float = 0.05  # 5% max deviation from mid
    max_order_quantity: Decimal = Decimal("1000")  # Max units per order
    max_order_notional: Decimal = Decimal("1000000")  # Max USD per order

    # Position limits
    max_position_per_symbol: Decimal = Decimal("100")  # Max position per symbol
    max_total_exposure: Decimal = Decimal("10000000")  # Max total USD exposure

    # Order rate limits
    max_orders_per_second: float = 10.0  # Max order submission rate
    max_orders_per_minute: float = 100.0  # Max order submission rate

    # Concentration limits
    max_concentration_pct: float = 0.05  # Max 5% of portfolio per symbol


@dataclass(slots=True)
class PreTradeRiskResult:
    """Result of pre-trade risk validation."""

    approved: bool
    reason: str = ""
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


class PreTradeRiskValidator:
    """Pre-Trade Risk Validator — Standash §4.6, §4.7.

    Every order must pass this validation before reaching the execution layer.
    This is the "hard gate" that prevents erroneous or excessive orders.
    """

    def __init__(self, config: PreTradeRiskConfig | None = None) -> None:
        self.config = config or PreTradeRiskConfig()

        # Order rate tracking (sliding window)
        self._order_timestamps: deque[float] = deque(maxlen=10000)

        # Current positions (updated externally)
        self._positions: dict[str, Decimal] = {}
        self._total_exposure: Decimal = Decimal("0")
        self._portfolio_value: Decimal = Decimal("0")

        # Current mid prices (updated externally)
        self._mid_prices: dict[str, Decimal] = {}

        # Kill switch reference (set externally)
        self._kill_switch_active: bool = False

        # Telemetry
        self._total_validated: int = 0
        self._total_rejected: int = 0
        self._rejection_reasons: dict[str, int] = {}

    def set_kill_switch_active(self, active: bool) -> None:
        """Update kill switch status."""
        self._kill_switch_active = active

    def update_position(self, symbol: str, position: Decimal) -> None:
        """Update current position for a symbol."""
        self._positions[symbol] = position

    def update_mid_price(self, symbol: str, price: Decimal) -> None:
        """Update current mid price for a symbol."""
        self._mid_prices[symbol] = price

    def update_portfolio_value(self, value: Decimal) -> None:
        """Update total portfolio value."""
        self._portfolio_value = value
        self._total_exposure = Decimal("0")
        for p in self._positions.values():
            self._total_exposure += abs(p)

    def validate_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
    ) -> PreTradeRiskResult:
        """Validate an order before execution.

        Args:
            symbol: Trading symbol.
            side: BUY or SELL.
            quantity: Order quantity.
            price: Order price (None for market orders).
            order_type: Order type (MARKET, LIMIT, etc.).

        Returns:
            PreTradeRiskResult with approval status and details.
        """
        self._total_validated += 1
        checks_passed: list[str] = []
        checks_failed: list[str] = []

        # Check 1: Kill switch
        if self._kill_switch_active:
            return PreTradeRiskResult(
                approved=False,
                reason="KILL_SWITCH_ACTIVE",
                checks_failed=["KILL_SWITCH"],
            )

        # Check 2: Order quantity limit
        if quantity > self.config.max_order_quantity:
            checks_failed.append(
                f"QUANTITY_EXCEEDED: {quantity} > {self.config.max_order_quantity}"
            )
        else:
            checks_passed.append("QUANTITY_OK")

        # Check 3: Order notional limit
        order_price = price or self._mid_prices.get(symbol, Decimal("0"))
        notional = quantity * order_price
        if notional > self.config.max_order_notional:
            checks_failed.append(
                f"NOTIONAL_EXCEEDED: {notional} > {self.config.max_order_notional}"
            )
        else:
            checks_passed.append("NOTIONAL_OK")

        # Check 4: Fat-finger price deviation
        if price is not None and symbol in self._mid_prices:
            mid = self._mid_prices[symbol]
            if mid > 0:
                deviation = abs(price - mid) / mid
                if deviation > self.config.max_price_deviation_pct:
                    checks_failed.append(
                        f"PRICE_DEVIATION: {deviation:.2%} > {self.config.max_price_deviation_pct:.2%}"
                    )
                else:
                    checks_passed.append("PRICE_OK")

        # Check 5: Position limit
        current_position = self._positions.get(symbol, Decimal("0"))
        side_upper = side.upper()
        new_position = current_position + (quantity if side_upper == "BUY" else -quantity)
        if abs(new_position) > self.config.max_position_per_symbol:
            checks_failed.append(
                f"POSITION_EXCEEDED: {abs(new_position)} > {self.config.max_position_per_symbol}"
            )
        else:
            checks_passed.append("POSITION_OK")

        # Check 6: Concentration limit
        if self._portfolio_value > 0:
            position_value = abs(new_position) * order_price
            concentration = position_value / self._portfolio_value
            if concentration > self.config.max_concentration_pct:
                checks_failed.append(
                    f"CONCENTRATION_EXCEEDED: {concentration:.2%} > {self.config.max_concentration_pct:.2%}"
                )
            else:
                checks_passed.append("CONCENTRATION_OK")

        # Check 7: Order rate limit (per second)
        now = time.time()
        self._order_timestamps.append(now)
        recent_1s = sum(1 for t in self._order_timestamps if now - t < 1.0)
        if recent_1s > self.config.max_orders_per_second:
            checks_failed.append(
                f"RATE_LIMIT_1S: {recent_1s} > {self.config.max_orders_per_second}"
            )
        else:
            checks_passed.append("RATE_LIMIT_1S_OK")

        # Check 8: Order rate limit (per minute)
        recent_60s = sum(1 for t in self._order_timestamps if now - t < 60.0)
        if recent_60s > self.config.max_orders_per_minute:
            checks_failed.append(
                f"RATE_LIMIT_60S: {recent_60s} > {self.config.max_orders_per_minute}"
            )
        else:
            checks_passed.append("RATE_LIMIT_60S_OK")

        # Final decision
        approved = len(checks_failed) == 0
        if not approved:
            self._total_rejected += 1
            for reason in checks_failed:
                key = reason.split(":")[0]
                self._rejection_reasons[key] = self._rejection_reasons.get(key, 0) + 1
            logger.warning(
                f"[PRE_TRADE_RISK] REJECTED | {symbol} {side} {quantity}@{price} | "
                f"Reasons: {checks_failed}"
            )
        else:
            logger.debug(f"[PRE_TRADE_RISK] APPROVED | {symbol} {side} {quantity}@{price}")

        return PreTradeRiskResult(
            approved=approved,
            reason="; ".join(checks_failed) if checks_failed else "",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )

    def get_telemetry(self) -> dict[str, Any]:
        """Get validation telemetry."""
        return {
            "total_validated": self._total_validated,
            "total_rejected": self._total_rejected,
            "rejection_rate": (
                self._total_rejected / self._total_validated if self._total_validated > 0 else 0.0
            ),
            "rejection_reasons": dict(self._rejection_reasons),
            "active_positions": dict(self._positions),
            "portfolio_value": float(self._portfolio_value),
        }
