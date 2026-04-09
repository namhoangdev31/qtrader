from __future__ import annotations
import logging
import math
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger("qtrader.execution.market_maker")


@dataclass(slots=True)
class Quote:
    symbol: str
    bid_price: Decimal
    ask_price: Decimal
    bid_size: Decimal
    ask_size: Decimal
    reservation_price: Decimal
    spread_bps: float
    timestamp: float = 0.0
    quote_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass(slots=True)
class InventoryState:
    symbol: str
    position: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    max_position: Decimal = Decimal("0")
    last_update: float = 0.0

    @property
    def inventory_risk(self) -> Decimal:
        return abs(self.position)

    @property
    def skew_direction(self) -> int:
        if self.position > 0:
            return -1
        elif self.position < 0:
            return 1
        return 0


@dataclass(slots=True)
class MarketMakerConfig:
    gamma: float = 0.1
    k: float = 1.5
    max_inventory: float = 10.0
    max_inventory_usd: float = 100000.0
    max_spread_bps: float = 100.0
    min_spread_bps: float = 5.0
    toxicity_withdrawal_threshold: float = 0.75
    toxicity_widen_threshold: float = 0.5
    toxicity_spread_multiplier: float = 2.0
    quote_update_interval_s: float = 0.1
    quote_staleness_timeout_s: float = 5.0
    max_quote_updates_per_second: float = 10.0
    vol_lookback_periods: int = 100
    vol_annualization_factor: float = 15768000


class MarketMakerEngine:
    def __init__(self, config: MarketMakerConfig | None = None) -> None:
        self.config = config or MarketMakerConfig()
        self._inventory: dict[str, InventoryState] = {}
        self._active_quotes: dict[str, Quote] = {}
        self._last_quote_update: dict[str, float] = {}
        self._quote_count: int = 0
        self._withdrawal_count: int = 0
        self._fill_count: int = 0
        self._total_spread_captured: Decimal = Decimal("0")

    def get_or_create_inventory(self, symbol: str) -> InventoryState:
        if symbol not in self._inventory:
            self._inventory[symbol] = InventoryState(
                symbol=symbol, max_position=Decimal(str(self.config.max_inventory))
            )
        return self._inventory[symbol]

    def update_inventory(
        self,
        symbol: str,
        fill_price: Decimal,
        fill_qty: Decimal,
        side: str,
        realized_pnl: Decimal = Decimal("0"),
    ) -> InventoryState:
        inv = self.get_or_create_inventory(symbol)
        qty = fill_qty if side == "BUY" else -fill_qty
        old_position = inv.position
        inv.position += qty
        if (
            old_position == 0
            or (old_position > 0 and inv.position > 0)
            or (old_position < 0 and inv.position < 0)
        ):
            total_qty = abs(inv.position)
            if total_qty > 0:
                inv.avg_entry_price = (
                    abs(old_position) * inv.avg_entry_price + fill_qty * fill_price
                ) / total_qty
        if abs(inv.position) > abs(inv.max_position):
            inv.max_position = abs(inv.position)
        inv.realized_pnl += realized_pnl
        inv.last_update = time.time()
        self._fill_count += 1
        logger.info(
            f"[MM_INVENTORY] {symbol} | Position: {inv.position} | Avg: {inv.avg_entry_price} | Realized PnL: {inv.realized_pnl}"
        )
        return inv

    def compute_quotes(
        self,
        symbol: str,
        mid_price: Decimal,
        volatility: float,
        toxicity_score: float = 0.0,
        queue_position: float = 0.5,
    ) -> Quote | None:
        inv = self.get_or_create_inventory(symbol)
        if inv.inventory_risk > inv.max_position:
            logger.warning(
                f"[MM_QUOTE] {symbol} | Inventory limit reached: {inv.inventory_risk} > {inv.max_position} — WITHDRAWING"
            )
            return None
        if toxicity_score > self.config.toxicity_withdrawal_threshold:
            self._withdrawal_count += 1
            logger.warning(
                f"[MM_QUOTE] {symbol} | Toxicity too high: {toxicity_score:.3f} — WITHDRAWING"
            )
            return None
        S = float(mid_price)
        q = float(inv.position)
        sigma = volatility
        reservation_price = S - q * self.config.gamma * sigma**2
        spread_risk = self.config.gamma * sigma**2
        spread_intensity = (
            2.0
            / (self.config.gamma + 1e-12)
            * math.log(1.0 + self.config.gamma / (self.config.k + 1e-12))
        )
        optimal_spread = spread_risk + spread_intensity
        if toxicity_score > self.config.toxicity_widen_threshold:
            optimal_spread *= self.config.toxicity_spread_multiplier
        if queue_position < 0.3:
            optimal_spread *= 1.2
        half_spread = optimal_spread / 2.0
        skew = q * self.config.gamma * sigma**2 * 0.5
        bid_price = reservation_price - half_spread - skew
        ask_price = reservation_price + half_spread - skew
        spread_bps = (ask_price - bid_price) / S * 10000 if S > 0 else 0
        if spread_bps > self.config.max_spread_bps:
            half_max = S * self.config.max_spread_bps / 20000
            bid_price = S - half_max
            ask_price = S + half_max
            spread_bps = self.config.max_spread_bps
        elif spread_bps < self.config.min_spread_bps:
            half_min = S * self.config.min_spread_bps / 20000
            bid_price = S - half_min
            ask_price = S + half_min
            spread_bps = self.config.min_spread_bps
        if bid_price >= ask_price:
            mid = (bid_price + ask_price) / 2
            tick = S * 0.0001
            bid_price = mid - tick
            ask_price = mid + tick
        bid_price = round(bid_price, 8)
        ask_price = round(ask_price, 8)
        self._quote_count += 1
        return Quote(
            symbol=symbol,
            bid_price=Decimal(str(bid_price)),
            ask_price=Decimal(str(ask_price)),
            bid_size=Decimal(str(self.config.max_inventory * 0.1)),
            ask_size=Decimal(str(self.config.max_inventory * 0.1)),
            reservation_price=Decimal(str(reservation_price)),
            spread_bps=spread_bps,
            timestamp=time.time(),
        )

    def should_update_quote(self, symbol: str) -> bool:
        last_update = self._last_quote_update.get(symbol, 0)
        now = time.time()
        if now - last_update > self.config.quote_staleness_timeout_s:
            return True
        min_interval = 1.0 / self.config.max_quote_updates_per_second
        if now - last_update >= min_interval:
            return True
        return False

    def register_quote(self, quote: Quote) -> None:
        self._active_quotes[quote.symbol] = quote
        self._last_quote_update[quote.symbol] = time.time()

    def withdraw_quote(self, symbol: str) -> None:
        self._active_quotes.pop(symbol, None)
        logger.info(f"[MM_QUOTE] {symbol} | Quote withdrawn")

    def get_inventory_summary(self) -> dict[str, Any]:
        return {
            sym: {
                "position": float(inv.position),
                "avg_entry_price": float(inv.avg_entry_price),
                "realized_pnl": float(inv.realized_pnl),
                "max_position": float(inv.max_position),
                "last_update": inv.last_update,
            }
            for (sym, inv) in self._inventory.items()
        }

    def get_active_quotes(self) -> dict[str, Any]:
        return {
            sym: {
                "bid": float(q.bid_price),
                "ask": float(q.ask_price),
                "spread_bps": q.spread_bps,
                "age_s": time.time() - q.timestamp,
            }
            for (sym, q) in self._active_quotes.items()
        }

    def get_telemetry(self) -> dict[str, Any]:
        return {
            "quote_count": self._quote_count,
            "withdrawal_count": self._withdrawal_count,
            "fill_count": self._fill_count,
            "active_symbols": len(self._active_quotes),
            "tracked_symbols": len(self._inventory),
            "config": {
                "gamma": self.config.gamma,
                "k": self.config.k,
                "max_inventory": self.config.max_inventory,
                "max_spread_bps": self.config.max_spread_bps,
                "toxicity_threshold": self.config.toxicity_withdrawal_threshold,
            },
        }
