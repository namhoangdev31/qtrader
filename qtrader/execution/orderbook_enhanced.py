import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import numpy as np
from qtrader.core.types import FillEvent, OrderEvent
from qtrader.execution.latency_model import LatencyModel
from qtrader.execution.slippage_model import SlippageModel

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderbookEnhanced:
    def __init__(
        self,
        symbols: list[str],
        base_spread_bps: float = 5.0,
        depth_levels: int = 10,
        volume_per_level: float = 1000.0,
        liquidity_decay_factor: float = 0.8,
    ) -> None:
        self.symbols = set(symbols)
        self.base_spread_bps = base_spread_bps
        self.depth_levels = depth_levels
        self.volume_per_level = volume_per_level
        self.liquidity_decay_factor = liquidity_decay_factor
        self._orderbooks: dict[str, dict] = {}
        self._last_update: dict[str, float] = {}
        for symbol in symbols:
            self._orderbooks[symbol] = self._generate_initial_orderbook(symbol)

    async def update_orderbook(self, symbol: str, market_data: Any) -> None:
        try:
            if symbol not in self._orderbooks:
                self._orderbooks[symbol] = self._generate_initial_orderbook(symbol)
            current_book = self._orderbooks[symbol]
            mid_price = self._get_mid_price(current_book)
            price_volatility = Decimal("0.001")
            price_change = Decimal(str(np.random.normal(0, float(price_volatility)))) * mid_price
            new_mid_price = mid_price + price_change
            if new_mid_price <= 0:
                new_mid_price = mid_price
            spread = new_mid_price * Decimal(str(self.base_spread_bps / 10000))
            half_spread = spread / Decimal("2")
            best_bid = new_mid_price - half_spread
            best_ask = new_mid_price + half_spread
            bids = []
            asks = []
            for i in range(self.depth_levels):
                distance_ticks = i + 1
                liquidity_multiplier = self.liquidity_decay_factor**distance_ticks
                level_volume = Decimal(str(self.volume_per_level)) * Decimal(
                    str(liquidity_multiplier)
                )
                volume_noise = Decimal(str(np.random.uniform(0.8, 1.2)))
                level_volume *= volume_noise
                bid_price = best_bid - Decimal(str(i)) * Decimal("0.01")
                ask_price = best_ask + Decimal(str(i)) * Decimal("0.01")
                if bid_price > 0 and ask_price > 0 and (bid_price < ask_price):
                    bids.append([bid_price, level_volume])
                    asks.append([ask_price, level_volume])
            self._orderbooks[symbol] = {
                "bids": bids,
                "asks": asks,
                "timestamp": asyncio.get_event_loop().time(),
            }
            self._last_update[symbol] = asyncio.get_event_loop().time()
            logger.debug(f"Updated orderbook for {symbol} - mid price: {new_mid_price:.2f}")
        except Exception as e:
            logger.error(f"Error updating orderbook for {symbol}: {e}", exc_info=True)

    async def get_orderbook(self, symbol: str) -> dict[str, Any] | None:
        if symbol not in self._orderbooks:
            logger.warning(f"No orderbook data for {symbol}, generating initial")
            self._orderbooks[symbol] = self._generate_initial_orderbook(symbol)
        ob = self._orderbooks[symbol]
        return {
            "symbol": ob["symbol"],
            "bids": [list(level) for level in ob.get("bids", [])],
            "asks": [list(level) for level in ob.get("asks", [])],
            "timestamp": ob.get("timestamp"),
        }

    def _generate_initial_orderbook(self, symbol: str) -> dict[str, Any]:
        base_price = Decimal("100.0")
        spread = base_price * Decimal(str(self.base_spread_bps / 10000))
        half_spread = spread / Decimal("2")
        best_bid = base_price - half_spread
        best_ask = base_price + half_spread
        bids = []
        asks = []
        for i in range(self.depth_levels):
            distance_ticks = i + 1
            liquidity_multiplier = self.liquidity_decay_factor**distance_ticks
            level_volume = Decimal(str(self.volume_per_level)) * Decimal(str(liquidity_multiplier))
            volume_noise = Decimal(str(np.random.uniform(0.5, 1.5)))
            level_volume *= volume_noise
            bid_price = best_bid - Decimal(str(i)) * Decimal("0.01")
            ask_price = best_ask + Decimal(str(i)) * Decimal("0.01")
            if bid_price > 0 and ask_price > 0:
                bids.append([bid_price, level_volume])
                asks.append([ask_price, level_volume])
        return {"bids": bids, "asks": asks, "timestamp": asyncio.get_event_loop().time()}

    def _get_mid_price(self, orderbook: dict[str, list]) -> Decimal:
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if not bids or not asks:
            return Decimal("0")
        try:
            best_bid = Decimal(str(bids[0][0]))
            best_ask = Decimal(str(asks[0][0]))
            return (best_bid + best_ask) / Decimal("2")
        except (IndexError, ValueError, TypeError):
            return Decimal("0")

    async def execute_order(
        self,
        symbol: str,
        order: OrderEvent,
        slippage_model: SlippageModel | None = None,
        latency_model: LatencyModel | None = None,
        maker_fee: Decimal = Decimal("0.001"),
        taker_fee: Decimal = Decimal("0.002"),
        deterministic: bool = False,
    ) -> FillEvent:
        latency_ms = 0.0
        if latency_model:
            latency_ms = await latency_model.get_latency()
        orderbook = await self.get_orderbook(symbol)
        if not orderbook:
            raise ValueError(f"No orderbook data for symbol {symbol}")
        if order.order_type.upper() == "MARKET":
            return await self._execute_market_order(
                symbol, order, orderbook, slippage_model, latency_ms, taker_fee, deterministic
            )
        elif order.order_type.upper() == "LIMIT":
            return await self._execute_limit_order(
                symbol,
                order,
                orderbook,
                slippage_model,
                latency_ms,
                maker_fee,
                taker_fee,
                deterministic,
            )
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

    async def _execute_market_order(
        self,
        symbol: str,
        order: OrderEvent,
        orderbook: dict[str, list],
        slippage_model: SlippageModel | None,
        latency_ms: float,
        taker_fee: Decimal,
        deterministic: bool,
    ) -> FillEvent:
        side = order.side.upper()
        quantity_to_fill = order.quantity
        filled_quantity = Decimal("0")
        total_cost = Decimal("0")
        fees = Decimal("0")
        if side == OrderSide.BUY.value:
            book_side = orderbook.get("asks", [])
            price_levels = book_side
        else:
            book_side = orderbook.get("bids", [])
            price_levels = list(reversed(book_side))
        for price_level in price_levels:
            if quantity_to_fill <= 0:
                break
            price = Decimal(str(price_level[0]))
            available_volume = Decimal(str(price_level[1]))
            fill_at_level = min(quantity_to_fill, available_volume)
            cost_at_level = fill_at_level * price
            if slippage_model and (not deterministic):
                total_volume_on_side = sum((Decimal(str(level[1])) for level in book_side))
                if total_volume_on_side > 0:
                    participation_rate = fill_at_level / total_volume_on_side
                    temp_slippage = slippage_model.temporary_impact * participation_rate * price
                    if side == OrderSide.BUY.value:
                        price += temp_slippage
                    else:
                        price -= temp_slippage
            filled_quantity += fill_at_level
            total_cost += cost_at_level
            quantity_to_fill -= fill_at_level
            fees += fill_at_level * price * taker_fee
            if fill_at_level < available_volume:
                break
        avg_price = total_cost / filled_quantity if filled_quantity > 0 else Decimal("0")
        fill_event = FillEvent(
            order_id=order.order_id,
            symbol=symbol,
            timestamp=datetime.now(),
            side=side,
            quantity=filled_quantity,
            price=avg_price,
            commission=fees,
            metadata={
                "latency_ms": latency_ms,
                "slippage_model_used": slippage_model is not None,
                "order_type": "MARKET",
                "fees_paid": float(fees),
                "average_price": float(avg_price),
            },
        )
        return fill_event

    async def _execute_limit_order(
        self,
        symbol: str,
        order: OrderEvent,
        orderbook: dict[str, list],
        slippage_model: SlippageModel | None,
        latency_ms: float,
        maker_fee: Decimal,
        taker_fee: Decimal,
        deterministic: bool,
    ) -> FillEvent:
        side = order.side.upper()
        limit_price = order.price if order.price is not None else Decimal("0")
        if limit_price <= 0:
            return await self._execute_market_order(
                symbol, order, orderbook, slippage_model, latency_ms, taker_fee, deterministic
            )
        is_marketable = False
        if side == OrderSide.BUY.value:
            best_ask = (
                Decimal(str(orderbook["asks"][0][0])) if orderbook.get("asks") else Decimal("0")
            )
            is_marketable = limit_price >= best_ask
        else:
            best_bid = (
                Decimal(str(orderbook["bids"][0][0])) if orderbook.get("bids") else Decimal("0")
            )
            is_marketable = limit_price <= best_bid
        if is_marketable:
            return await self._execute_market_order(
                symbol, order, orderbook, slippage_model, latency_ms, taker_fee, deterministic
            )
        else:
            filled_quantity = order.quantity
            filled_quantity * limit_price
            fees = filled_quantity * limit_price * maker_fee
            fill_event = FillEvent(
                order_id=order.order_id,
                symbol=symbol,
                timestamp=datetime.now(),
                side=side,
                quantity=filled_quantity,
                price=limit_price,
                commission=fees,
                metadata={
                    "latency_ms": latency_ms,
                    "slippage_model_used": slippage_model is not None,
                    "order_type": "LIMIT",
                    "fees_paid": float(fees),
                    "average_price": float(limit_price),
                    "was_marketable": False,
                },
            )
            return fill_event

    def get_liquidity_profile(self, symbol: str) -> dict[str, Any]:
        orderbook = self._orderbooks.get(symbol)
        if not orderbook:
            return {}
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        bid_depth_1: Decimal = sum((Decimal(str(level[1])) for level in bids[:1]), Decimal("0"))
        bid_depth_5: Decimal = sum((Decimal(str(level[1])) for level in bids[:5]), Decimal("0"))
        bid_depth_10: Decimal = sum((Decimal(str(level[1])) for level in bids[:10]), Decimal("0"))
        ask_depth_1: Decimal = sum((Decimal(str(level[1])) for level in asks[:1]), Decimal("0"))
        ask_depth_5: Decimal = sum((Decimal(str(level[1])) for level in asks[:5]), Decimal("0"))
        ask_depth_10: Decimal = sum((Decimal(str(level[1])) for level in asks[:10]), Decimal("0"))

        def weighted_avg_price(levels):
            if not levels:
                return Decimal("0")
            total_value: Decimal = sum(
                (Decimal(str(level[0])) * Decimal(str(level[1])) for level in levels), Decimal("0")
            )
            total_volume: Decimal = sum((Decimal(str(level[1])) for level in levels), Decimal("0"))
            return total_value / total_volume if total_volume > 0 else Decimal("0")

        bid_wap: Decimal = weighted_avg_price(bids[:5])
        ask_wap: Decimal = weighted_avg_price(asks[:5])
        spread_bps = 0.0
        if bid_wap > 0:
            spread = Decimal(str(ask_wap)) - Decimal(str(bid_wap))
            spread_bps = float(spread / Decimal(str(bid_wap)) * Decimal("10000"))
        return {
            "bid_depth_1": float(bid_depth_1),
            "bid_depth_5": float(bid_depth_5),
            "bid_depth_10": float(bid_depth_10),
            "ask_depth_1": float(ask_depth_1),
            "ask_depth_5": float(ask_depth_5),
            "ask_depth_10": float(ask_depth_10),
            "bid_wap_5": float(bid_wap),
            "ask_wap_5": float(ask_wap),
            "spread_bps": spread_bps,
        }
