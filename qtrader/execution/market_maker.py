"""Market Maker Quoting Engine — Standash §4.7, §4.8.

Avellaneda-Stoikov market making strategy with:
- Real-time inventory tracking and risk management
- Dynamic quote generation based on volatility, inventory, and toxicity
- Quote lifecycle management (post → monitor → cancel → replace)
- Adverse selection protection (quote withdrawal on high toxicity)
- Multi-symbol quoting orchestration
"""

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
    """A single two-sided quote for a symbol."""

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
    """Real-time inventory state for a single symbol."""

    symbol: str
    position: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    max_position: Decimal = Decimal("0")
    last_update: float = 0.0

    @property
    def inventory_risk(self) -> Decimal:
        """Absolute inventory exposure."""
        return abs(self.position)

    @property
    def skew_direction(self) -> int:
        """Direction to skew quotes based on inventory.

        Positive inventory (long) → skew quotes down (encourage selling)
        Negative inventory (short) → skew quotes up (encourage buying)
        """
        if self.position > 0:
            return -1
        elif self.position < 0:
            return 1
        return 0


@dataclass(slots=True)
class MarketMakerConfig:
    """Configuration for the Market Maker engine."""

    # Avellaneda-Stoikov parameters
    gamma: float = 0.1  # Risk aversion (inventory penalty)
    k: float = 1.5  # Order arrival rate (market depth)

    # Risk limits
    max_inventory: float = 10.0  # Max absolute position per symbol
    max_inventory_usd: float = 100_000.0  # Max USD exposure per symbol
    max_spread_bps: float = 100.0  # Max quoted spread (100 bps)
    min_spread_bps: float = 5.0  # Min quoted spread (5 bps)

    # Toxicity thresholds
    toxicity_withdrawal_threshold: float = 0.75  # Pull quotes above this
    toxicity_widen_threshold: float = 0.50  # Widen spread above this
    toxicity_spread_multiplier: float = 2.0  # Spread multiplier when toxic

    # Quote management
    quote_update_interval_s: float = 0.1  # Min time between quote updates
    quote_staleness_timeout_s: float = 5.0  # Max age before quote refresh
    max_quote_updates_per_second: float = 10.0  # Rate limit

    # Volatility scaling
    vol_lookback_periods: int = 100  # Rolling vol window
    vol_annualization_factor: float = 15_768_000  # sqrt(seconds per year)


class MarketMakerEngine:
    """Market Maker Quoting Engine — Standash §4.7, §4.8.

    Implements the Avellaneda-Stoikov market making model with:
    - Reservation price: r = S - q * γ * σ²
    - Optimal spread: δ = γσ² + (2/γ) * ln(1 + γ/k)
    - Bid quote: r - δ/2, Ask quote: r + δ/2

    Enhanced with:
    - Real-time inventory tracking per symbol
    - Adverse selection protection (toxicity-based quote withdrawal)
    - Queue position awareness (from QueuePositionModel)
    - Quote lifecycle management with rate limiting
    - Multi-symbol orchestration
    """

    def __init__(self, config: MarketMakerConfig | None = None) -> None:
        self.config = config or MarketMakerConfig()

        # Per-symbol inventory tracking
        self._inventory: dict[str, InventoryState] = {}

        # Active quotes per symbol
        self._active_quotes: dict[str, Quote] = {}

        # Quote update timestamps (for rate limiting)
        self._last_quote_update: dict[str, float] = {}

        # Telemetry
        self._quote_count: int = 0
        self._withdrawal_count: int = 0
        self._fill_count: int = 0
        self._total_spread_captured: Decimal = Decimal("0")

    def get_or_create_inventory(self, symbol: str) -> InventoryState:
        """Get or create inventory state for a symbol."""
        if symbol not in self._inventory:
            self._inventory[symbol] = InventoryState(
                symbol=symbol,
                max_position=Decimal(str(self.config.max_inventory)),
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
        """Update inventory after a fill.

        Args:
            symbol: Trading symbol.
            fill_price: Execution price.
            fill_qty: Fill quantity (positive).
            side: BUY or SELL.
            realized_pnl: PnL realized from this fill (if closing position).
        """
        inv = self.get_or_create_inventory(symbol)

        # Update position
        qty = fill_qty if side == "BUY" else -fill_qty
        old_position = inv.position
        inv.position += qty

        # Update average entry price (only when adding to position)
        if (
            (old_position == 0)
            or (old_position > 0 and inv.position > 0)
            or (old_position < 0 and inv.position < 0)
        ):
            total_qty = abs(inv.position)
            if total_qty > 0:
                inv.avg_entry_price = (
                    abs(old_position) * inv.avg_entry_price + fill_qty * fill_price
                ) / total_qty

        # Track max position
        if abs(inv.position) > abs(inv.max_position):
            inv.max_position = abs(inv.position)

        # Update PnL
        inv.realized_pnl += realized_pnl

        # Update unrealized PnL (needs current mid price, set externally)
        inv.last_update = time.time()

        self._fill_count += 1

        logger.info(
            f"[MM_INVENTORY] {symbol} | Position: {inv.position} | "
            f"Avg: {inv.avg_entry_price} | Realized PnL: {inv.realized_pnl}"
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
        """Compute optimal bid/ask quotes using Avellaneda-Stoikov model.

        Args:
            symbol: Trading symbol.
            mid_price: Current mid price (S).
            volatility: Rolling volatility (σ, annualized).
            toxicity_score: Adverse selection score [0, 1].
            queue_position: Estimated queue position [0, 1].

        Returns:
            Quote object, or None if quotes should be withdrawn.
        """
        inv = self.get_or_create_inventory(symbol)

        # Check inventory limits
        if inv.inventory_risk > inv.max_position:
            logger.warning(
                f"[MM_QUOTE] {symbol} | Inventory limit reached: "
                f"{inv.inventory_risk} > {inv.max_position} — WITHDRAWING"
            )
            return None

        # Check toxicity — withdraw quotes if too toxic
        if toxicity_score > self.config.toxicity_withdrawal_threshold:
            self._withdrawal_count += 1
            logger.warning(
                f"[MM_QUOTE] {symbol} | Toxicity too high: {toxicity_score:.3f} — WITHDRAWING"
            )
            return None

        # Convert to float for computation
        S = float(mid_price)
        q = float(inv.position)
        sigma = volatility

        # 1. Reservation Price: r = S - q * γ * σ²
        reservation_price = S - q * self.config.gamma * (sigma**2)

        # 2. Optimal Spread: δ = γσ² + (2/γ) * ln(1 + γ/k)
        spread_risk = self.config.gamma * (sigma**2)
        spread_intensity = (2.0 / (self.config.gamma + 1e-12)) * math.log(
            1.0 + self.config.gamma / (self.config.k + 1e-12)
        )
        optimal_spread = spread_risk + spread_intensity

        # 3. Toxicity adjustment: widen spread when market is toxic
        if toxicity_score > self.config.toxicity_widen_threshold:
            optimal_spread *= self.config.toxicity_spread_multiplier

        # 4. Queue position adjustment: widen if queue position is poor
        if queue_position < 0.3:  # Far from front of queue
            optimal_spread *= 1.2  # 20% wider

        # 5. Convert spread to absolute price
        half_spread = optimal_spread / 2.0

        # 6. Inventory skew: skew quotes toward reducing inventory
        skew = q * self.config.gamma * (sigma**2) * 0.5

        # 7. Final quotes
        bid_price = reservation_price - half_spread - skew
        ask_price = reservation_price + half_spread - skew

        # 8. Validate spread bounds
        spread_bps = (ask_price - bid_price) / S * 10000 if S > 0 else 0
        if spread_bps > self.config.max_spread_bps:
            # Clamp to max spread
            half_max = S * self.config.max_spread_bps / 20000
            bid_price = S - half_max
            ask_price = S + half_max
            spread_bps = self.config.max_spread_bps
        elif spread_bps < self.config.min_spread_bps:
            half_min = S * self.config.min_spread_bps / 20000
            bid_price = S - half_min
            ask_price = S + half_min
            spread_bps = self.config.min_spread_bps

        # 9. Ensure bid < ask
        if bid_price >= ask_price:
            mid = (bid_price + ask_price) / 2
            tick = S * 0.0001  # 1 bps minimum
            bid_price = mid - tick
            ask_price = mid + tick

        # 10. Round to reasonable precision
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
        """Check if quote should be updated (rate limiting + staleness)."""
        last_update = self._last_quote_update.get(symbol, 0)
        now = time.time()

        # Check staleness
        if now - last_update > self.config.quote_staleness_timeout_s:
            return True

        # Check rate limit
        min_interval = 1.0 / self.config.max_quote_updates_per_second
        if now - last_update >= min_interval:
            return True

        return False

    def register_quote(self, quote: Quote) -> None:
        """Register an active quote."""
        self._active_quotes[quote.symbol] = quote
        self._last_quote_update[quote.symbol] = time.time()

    def withdraw_quote(self, symbol: str) -> None:
        """Withdraw a quote (e.g., on toxicity or inventory limit)."""
        self._active_quotes.pop(symbol, None)
        logger.info(f"[MM_QUOTE] {symbol} | Quote withdrawn")

    def get_inventory_summary(self) -> dict[str, Any]:
        """Get inventory summary for all symbols."""
        return {
            sym: {
                "position": float(inv.position),
                "avg_entry_price": float(inv.avg_entry_price),
                "realized_pnl": float(inv.realized_pnl),
                "max_position": float(inv.max_position),
                "last_update": inv.last_update,
            }
            for sym, inv in self._inventory.items()
        }

    def get_active_quotes(self) -> dict[str, Any]:
        """Get all active quotes."""
        return {
            sym: {
                "bid": float(q.bid_price),
                "ask": float(q.ask_price),
                "spread_bps": q.spread_bps,
                "age_s": time.time() - q.timestamp,
            }
            for sym, q in self._active_quotes.items()
        }

    def get_telemetry(self) -> dict[str, Any]:
        """Get engine telemetry."""
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
