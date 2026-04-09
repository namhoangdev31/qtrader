from __future__ import annotations
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from qtrader.core.dynamic_config import DynamicSettingsMixin

logger = logging.getLogger("qtrader.execution.pre_trade_risk")
try:
    import qtrader_core
    from qtrader_core import Side as RustSide

    HAS_RUST_CORE = True
except ImportError:
    HAS_RUST_CORE = False


@dataclass(slots=True)
class PreTradeRiskConfig:
    max_price_deviation_pct: float = 0.05
    max_order_quantity: Decimal = Decimal("1000")
    max_order_notional: Decimal = Decimal("1000000")
    max_position_per_symbol: Decimal = Decimal("100")
    max_position_usd: Decimal = Decimal("1000000")
    max_total_exposure: Decimal = Decimal("10000000")
    max_orders_per_second: float = 10.0
    max_orders_per_minute: float = 100.0
    max_concentration_pct: float = 0.05


@dataclass(slots=True)
class PreTradeRiskResult:
    approved: bool
    reason: str = ""
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


class PreTradeRiskValidator(DynamicSettingsMixin):
    def __init__(self, config: PreTradeRiskConfig | None = None) -> None:
        self.config = config or PreTradeRiskConfig()
        self._order_timestamps: deque[float] = deque(maxlen=10000)
        self._positions: dict[str, Decimal] = {}
        self._total_exposure: Decimal = Decimal("0")
        self._portfolio_value: Decimal = Decimal("0")
        self._mid_prices: dict[str, Decimal] = {}
        self._kill_switch_active: bool = False
        self._total_validated: int = 0
        self._total_rejected: int = 0
        self._rejection_reasons: dict[str, int] = {}
        self._effective_unit_limits: dict[str, Decimal] = {}
        if HAS_RUST_CORE:
            self._rust_engine = qtrader_core.RiskEngine(
                max_position_usd=float(
                    self.config.max_position_per_symbol
                    * (self.config.max_order_notional / self.config.max_order_quantity)
                ),
                max_drawdown_pct=float(self.config.max_concentration_pct),
                max_order_qty=float(self.config.max_order_quantity),
                max_order_notional=float(self.config.max_order_notional),
                max_orders_per_second=int(self.config.max_orders_per_second),
                max_price_deviation_pct=float(self.config.max_price_deviation_pct),
            )
            self._rust_engine.max_position_usd = float(self.config.max_total_exposure)

    def set_kill_switch_active(self, active: bool) -> None:
        self._kill_switch_active = active

    def update_position(self, symbol: str, position: Decimal) -> None:
        self._positions[symbol] = position

    def update_mid_price(self, symbol: str, price: Decimal) -> None:
        self._mid_prices[symbol] = price
        if price > 0:
            self._effective_unit_limits[symbol] = self.config.max_position_usd / price
            logger.debug(
                f"[RISK] Recalculated dynamic unit limit for {symbol}: {self._effective_unit_limits[symbol]:.4f}"
            )

    def update_portfolio_value(self, value: Decimal) -> None:
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
        self._total_validated += 1
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        if self._kill_switch_active:
            return PreTradeRiskResult(
                approved=False, reason="KILL_SWITCH_ACTIVE", checks_failed=["KILL_SWITCH"]
            )
        if quantity > self.config.max_order_quantity:
            checks_failed.append(
                f"QUANTITY_EXCEEDED: {quantity} > {self.config.max_order_quantity}"
            )
        else:
            checks_passed.append("QUANTITY_OK")
        order_price = price or self._mid_prices.get(symbol, Decimal("0"))
        notional = quantity * order_price
        if notional > self.config.max_order_notional:
            checks_failed.append(
                f"NOTIONAL_EXCEEDED: {notional} > {self.config.max_order_notional}"
            )
        else:
            checks_passed.append("NOTIONAL_OK")
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
        current_position = self._positions.get(symbol, Decimal("0"))
        side_upper = side.upper()
        new_position = current_position + (quantity if side_upper == "BUY" else -quantity)
        effective_limit = self._effective_unit_limits.get(
            symbol, self.config.max_position_per_symbol
        )
        if abs(new_position) > effective_limit:
            checks_failed.append(
                f"POSITION_UNITS_EXCEEDED: {abs(new_position):.4f} > {effective_limit:.4f} (Dynamic)"
            )
        else:
            checks_passed.append("POSITION_UNITS_OK")
        current_mid = self._mid_prices.get(symbol, order_price)
        if current_mid > 0:
            new_position_usd = abs(new_position) * current_mid
            if new_position_usd > self.config.max_position_usd:
                checks_failed.append(
                    f"POSITION_USD_EXCEEDED: ${new_position_usd:,.2f} > ${self.config.max_position_usd:,.2f}"
                )
            else:
                checks_passed.append("POSITION_USD_OK")
        if self._portfolio_value > 0:
            position_value = abs(new_position) * order_price
            concentration = position_value / self._portfolio_value
            if concentration > self.config.max_concentration_pct:
                checks_failed.append(
                    f"CONCENTRATION_EXCEEDED: {concentration:.2%} > {self.config.max_concentration_pct:.2%}"
                )
            else:
                checks_passed.append("CONCENTRATION_OK")
        now = time.time()
        self._order_timestamps.append(now)
        max_ops = self.TS_MAX_ORDERS_PER_SECOND
        recent_1s = sum((1 for t in self._order_timestamps if now - t < 1.0))
        if recent_1s > max_ops:
            checks_failed.append(
                f"RATE_LIMIT_1S: {recent_1s} > {max_ops} orders/sec (DYNAMIC_OVERRIDE_ACTIVE)"
            )
        else:
            checks_passed.append("RATE_LIMIT_1S_OK")
        recent_60s = sum((1 for t in self._order_timestamps if now - t < 60.0))
        max_opm = self.config.max_orders_per_minute
        if recent_60s > max_opm:
            checks_failed.append(f"RATE_LIMIT_60S: {recent_60s} > {max_opm}")
        else:
            checks_passed.append("RATE_LIMIT_60S_OK")
        if HAS_RUST_CORE:
            from qtrader_core import Account as RustAccount
            from qtrader_core import Order as RustOrder
            from qtrader_core import OrderType as RustOrderType
            from qtrader_core import Side as RustSide

            rust_side = RustSide.Buy if side.upper() == "BUY" else RustSide.Sell
            order_price_f = float(price or self._mid_prices.get(symbol, Decimal("0")))
            rust_order = RustOrder(
                0,
                symbol,
                rust_side,
                float(quantity),
                order_price_f,
                RustOrderType.Limit if price else RustOrderType.Market,
                int(time.time() * 1000),
            )
            rust_account = RustAccount(float(self._portfolio_value))
            for sym, qty in self._positions.items():
                rust_account.add_position_direct(
                    sym, float(qty), float(self._mid_prices.get(sym, Decimal("0")))
                )
            try:
                self._rust_engine.check_order(
                    rust_order, rust_account, order_price_f, float(self._portfolio_value)
                )
                checks_passed.extend(["RUST_FAT_FINGER_OK", "RUST_POSITION_OK"])
            except ValueError as e:
                checks_failed.append(f"RUST_RISK_REJECT: {e!s}")
        approved = len(checks_failed) == 0
        if not approved:
            self._total_rejected += 1
            for reason in checks_failed:
                key = reason.split(":")[0]
                self._rejection_reasons[key] = self._rejection_reasons.get(key, 0) + 1
            logger.warning(
                f"[PRE_TRADE_RISK] REJECTED | {symbol} {side} {quantity}@{price} | Reasons: {checks_failed}"
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
        return {
            "total_validated": self._total_validated,
            "total_rejected": self._total_rejected,
            "rejection_rate": self._total_rejected / self._total_validated
            if self._total_validated > 0
            else 0.0,
            "rejection_reasons": dict(self._rejection_reasons),
            "active_positions": dict(self._positions),
            "portfolio_value": float(self._portfolio_value),
        }
