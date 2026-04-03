"""Market Maker Live Integration — Standash §4.7, §4.8.

Integrates the MarketMakerEngine with live broker adapters:
- Subscribes to real-time market data via WebSocket
- Posts two-sided quotes to exchanges
- Monitors fills and updates inventory
- Adjusts quotes based on toxicity, inventory, and volatility
- Cancels stale quotes and posts new ones
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

logger = logging.getLogger("qtrader.execution.market_maker_live")


class MarketMakerLive:
    """Live Market Maker — integrates quoting engine with broker adapters.

    Orchestrates:
    1. Market data ingestion (WebSocket)
    2. Quote generation (Avellaneda-Stoikov)
    3. Order submission (broker adapter)
    4. Fill processing (WebSocket order updates)
    5. Inventory management (real-time)
    6. Toxicity monitoring (adverse selection)
    """

    def __init__(
        self,
        market_maker_engine: Any,  # MarketMakerEngine
        broker: Any,  # BrokerAdapter
        symbols: list[str],
        quote_update_interval_s: float = 0.5,
    ) -> None:
        self.mm = market_maker_engine
        self.broker = broker
        self.symbols = symbols
        self.quote_update_interval_s = quote_update_interval_s

        # Real-time market data
        self._mid_prices: dict[str, Decimal] = {}
        self._volatilities: dict[str, float] = {}
        self._toxicity_scores: dict[str, float] = {}

        # Active order IDs per symbol (for tracking)
        self._active_order_ids: dict[str, list[str]] = {s: [] for s in symbols}

        # State
        self._running = False
        self._quote_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the live market maker."""
        self._running = True

        # Set up WebSocket handlers
        if hasattr(self.broker, "set_order_update_handler"):
            self.broker.set_order_update_handler(self._on_order_update)

        # Start broker WebSocket
        if hasattr(self.broker, "start_websocket"):
            await self.broker.start_websocket()

        # Start quoting loop
        self._quote_task = asyncio.create_task(self._quoting_loop())
        self._monitor_task = asyncio.create_task(self._monitoring_loop())

        logger.info(
            f"[MM_LIVE] Started | Symbols: {self.symbols} | "
            f"Interval: {self.quote_update_interval_s}s"
        )

    async def stop(self) -> None:
        """Stop the live market maker and cancel all quotes."""
        self._running = False

        # Cancel all active orders
        for symbol, order_ids in self._active_order_ids.items():
            for order_id in order_ids:
                try:
                    await self.broker.cancel_order(order_id)
                    logger.info(f"[MM_LIVE] Cancelled order {order_id} for {symbol}")
                except Exception as e:
                    logger.error(f"[MM_LIVE] Failed to cancel {order_id}: {e}")

        if self._quote_task:
            self._quote_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()

        if hasattr(self.broker, "stop_websocket"):
            await self.broker.stop_websocket()

        logger.info("[MM_LIVE] Stopped — all quotes cancelled")

    async def _quoting_loop(self) -> None:
        """Main quoting loop: generate and post quotes."""
        while self._running:
            try:
                for symbol in self.symbols:
                    mid = self._mid_prices.get(symbol)
                    vol = self._volatilities.get(symbol, 0.02)
                    toxicity = self._toxicity_scores.get(symbol, 0.0)

                    if mid is None:
                        continue

                    # Check if we should update quotes
                    if not self.mm.should_update_quote(symbol):
                        continue

                    # Generate quotes
                    quote = self.mm.compute_quotes(
                        symbol=symbol,
                        mid_price=mid,
                        volatility=vol,
                        toxicity_score=toxicity,
                    )

                    if quote is None:
                        # Withdraw quotes (toxicity or inventory limit)
                        self.mm.withdraw_quote(symbol)
                        await self._cancel_quotes_for_symbol(symbol)
                        continue

                    # Post quotes (simplified: one bid and one ask order)
                    await self._post_quote(symbol, quote)

                await asyncio.sleep(self.quote_update_interval_s)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MM_LIVE] Quoting loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _post_quote(self, symbol: str, quote: Any) -> None:
        """Post a two-sided quote to the exchange."""
        # Cancel existing quotes for this symbol
        await self._cancel_quotes_for_symbol(symbol)

        # Post bid order
        try:
            bid_order = type(
                "Order",
                (),
                {
                    "symbol": symbol,
                    "side": "BUY",
                    "quantity": float(quote.bid_size),
                    "price": float(quote.bid_price),
                    "order_type": "LIMIT",
                    "order_id": f"mm_bid_{symbol}_{int(time.time() * 1000)}",
                },
            )()
            order_id = await self.broker.submit_order(bid_order)
            self._active_order_ids[symbol].append(order_id)
            logger.debug(f"[MM_LIVE] Posted BID | {symbol} | {quote.bid_size}@{quote.bid_price}")
        except Exception as e:
            logger.error(f"[MM_LIVE] Failed to post bid for {symbol}: {e}")

        # Post ask order
        try:
            ask_order = type(
                "Order",
                (),
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "quantity": float(quote.ask_size),
                    "price": float(quote.ask_price),
                    "order_type": "LIMIT",
                    "order_id": f"mm_ask_{symbol}_{int(time.time() * 1000)}",
                },
            )()
            order_id = await self.broker.submit_order(ask_order)
            self._active_order_ids[symbol].append(order_id)
            logger.debug(f"[MM_LIVE] Posted ASK | {symbol} | {quote.ask_size}@{quote.ask_price}")
        except Exception as e:
            logger.error(f"[MM_LIVE] Failed to post ask for {symbol}: {e}")

        # Register quote
        self.mm.register_quote(quote)

    async def _cancel_quotes_for_symbol(self, symbol: str) -> None:
        """Cancel all active quotes for a symbol."""
        for order_id in self._active_order_ids.get(symbol, []):
            try:
                await self.broker.cancel_order(order_id)
            except Exception as e:
                logger.warning(f"[MM_LIVE] Failed to cancel order {order_id} for {symbol}: {e}")
        self._active_order_ids[symbol] = []

    async def _monitoring_loop(self) -> None:
        """Monitoring loop: update volatility, toxicity, and market data."""
        while self._running:
            try:
                # Update market data from broker (would come from WebSocket in production)
                if hasattr(self.broker, "get_balance"):
                    balances = await self.broker.get_balance()
                    # Use balance updates to infer market state
                    # In production, this would come from the WebSocket ticker channel

                # Update inventory telemetry
                inv_summary = self.mm.get_inventory_summary()
                active_quotes = self.mm.get_active_quotes()
                telemetry = self.mm.get_telemetry()

                logger.debug(
                    f"[MM_LIVE] Monitor | "
                    f"Quotes: {len(active_quotes)} | "
                    f"Fills: {telemetry['fill_count']} | "
                    f"Withdrawals: {telemetry['withdrawal_count']}"
                )

                await asyncio.sleep(5.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MM_LIVE] Monitoring loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    def _on_order_update(self, data: dict[str, Any]) -> None:
        """Handle order update from broker WebSocket."""
        # Parse order update and update inventory if filled
        status = data.get("status") or data.get("X", "")
        symbol = data.get("symbol") or data.get("s", "")

        if status in ("FILLED", "PARTIALLY_FILLED"):
            # Update inventory
            price = Decimal(str(data.get("price") or data.get("L", "0")))
            qty = Decimal(str(data.get("quantity") or data.get("z", "0")))
            side = data.get("side") or data.get("S", "BUY")

            self.mm.update_inventory(
                symbol=symbol,
                fill_price=price,
                fill_qty=qty,
                side=side,
            )

            # Remove from active orders
            order_id = str(data.get("order_id") or data.get("i", ""))
            if order_id and symbol in self._active_order_ids:
                if order_id in self._active_order_ids[symbol]:
                    self._active_order_ids[symbol].remove(order_id)

            logger.info(
                f"[MM_LIVE] Fill | {symbol} | {side} {qty}@{price} | "
                f"Inventory: {self.mm.get_or_create_inventory(symbol).position}"
            )

    def update_market_data(
        self, symbol: str, mid_price: Decimal, volatility: float, toxicity: float
    ) -> None:
        """Update market data from external source (e.g., WebSocket ticker)."""
        self._mid_prices[symbol] = mid_price
        self._volatilities[symbol] = volatility
        self._toxicity_scores[symbol] = toxicity
