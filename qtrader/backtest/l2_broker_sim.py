import asyncio
from loguru import logger
import uuid
from dataclasses import dataclass

from qtrader.core.bus import EventBus
from qtrader.core.event import FillEvent, MarketDataEvent, OrderEvent


@dataclass
class QueueOrder:
    order_id: str
    order: OrderEvent
    price: float
    volume_ahead: float
    remaining_qty: float
    timestamp: float


class L2BrokerSim:
    """
    Advanced Simulator for L2 Orderbook.
    Simulates:
    - Queue position (orders only fill after volume ahead is consumed)
    - Network Latency
    - Partial Fills
    """
    def __init__(self, bus: EventBus, latency_ms: int = 5) -> None:
        self.bus = bus
        self.latency_ms = latency_ms / 1000.0
        self.bid_queue: list[QueueOrder] = []
        self.ask_queue: list[QueueOrder] = []
        self.market_buy: list[QueueOrder] = []
        self.market_sell: list[QueueOrder] = []
        # current orderbook state
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.bid_size = 0.0
        self.ask_size = 0.0

    async def on_market_data(self, event: MarketDataEvent) -> None:
        """Process incoming L2 snapshots/deltas and update queues."""
        data = event.data
        self.best_bid = data.get("bid", self.best_bid)
        self.best_ask = data.get("ask", self.best_ask)
        self.bid_size = data.get("bid_size", self.bid_size)
        self.ask_size = data.get("ask_size", self.ask_size)

        # 1) Fill queued market orders at current best prices.
        await self._fill_market_orders()

        # 2) Apply trade prints (queue depletion + partial fills).
        trade_price = data.get("trade_price")
        trade_qty = data.get("trade_qty")
        trade_side = data.get("trade_side")
        if trade_price is not None and trade_qty is not None and trade_side is not None:
            await self._apply_trade_logger.info(
                trade_price=float(trade_price),
                trade_qty=float(trade_qty),
                trade_side=str(trade_side).upper(),
            )

        # 3) Fill any crossing limit orders using current best prices.
        await self._fill_crossing_limits()

    async def on_order(self, order: OrderEvent) -> None:
        """Simulate sending order with latency."""
        await asyncio.sleep(self.latency_ms)

        oid = order.order_id or str(uuid.uuid4())
        side = order.side.upper()
        order_type = order.order_type.upper()

        if order_type == "MARKET":
            if side == "BUY" and self.best_ask > 0.0:
                await self._execute_fill(
                    QueueOrder(
                        oid,
                        order,
                        price=self.best_ask,
                        volume_ahead=0.0,
                        remaining_qty=float(order.quantity),
                        timestamp=asyncio.get_event_loop().time(),
                    ),
                    self.best_ask,
                    float(order.quantity),
                )
                return
            if side == "SELL" and self.best_bid > 0.0:
                await self._execute_fill(
                    QueueOrder(
                        oid,
                        order,
                        price=self.best_bid,
                        volume_ahead=0.0,
                        remaining_qty=float(order.quantity),
                        timestamp=asyncio.get_event_loop().time(),
                    ),
                    self.best_bid,
                    float(order.quantity),
                )
                return

            # If we don't have a book yet, queue market order.
            qo = QueueOrder(
                order_id=oid,
                order=order,
                price=0.0,
                volume_ahead=0.0,
                remaining_qty=float(order.quantity),
                timestamp=asyncio.get_event_loop().time(),
            )
            if side == "BUY":
                self.market_buy.append(qo)
            else:
                self.market_sell.append(qo)
            return

        # LIMIT orders
        limit_px = float(order.price or 0.0)
        if limit_px <= 0.0:
            return

        # Aggressive limit that crosses the book fills immediately.
        if side == "BUY" and self.best_ask > 0.0 and limit_px >= self.best_ask:
            await self._execute_fill(
                QueueOrder(
                    oid,
                    order,
                    price=self.best_ask,
                    volume_ahead=0.0,
                    remaining_qty=float(order.quantity),
                    timestamp=asyncio.get_event_loop().time(),
                ),
                self.best_ask,
                float(order.quantity),
            )
            return
        if side == "SELL" and self.best_bid > 0.0 and limit_px <= self.best_bid:
            await self._execute_fill(
                QueueOrder(
                    oid,
                    order,
                    price=self.best_bid,
                    volume_ahead=0.0,
                    remaining_qty=float(order.quantity),
                    timestamp=asyncio.get_event_loop().time(),
                ),
                self.best_bid,
                float(order.quantity),
            )
            return

        # Queue at price with price-time priority.
        volume_ahead = self._estimate_volume_ahead(side=side, price=limit_px)
        qo = QueueOrder(
            order_id=oid,
            order=order,
            price=limit_px,
            volume_ahead=volume_ahead,
            remaining_qty=float(order.quantity),
            timestamp=asyncio.get_event_loop().time(),
        )
        if side == "BUY":
            self.bid_queue.append(qo)
        else:
            self.ask_queue.append(qo)

    async def _execute_fill(self, q_order: QueueOrder, price: float, quantity: float) -> None:
        fill = FillEvent(
            symbol=q_order.order.symbol,
            quantity=quantity,
            price=price,
            commission=0.0,
            side=q_order.order.side,
            order_id=q_order.order.order_id or q_order.order_id,
            fill_id=str(uuid.uuid4()),
        )
        await self.bus.publish(fill)

    def _estimate_volume_ahead(self, *, side: str, price: float) -> float:
        """Estimate queued volume ahead at the price level (price-time priority)."""
        if side == "BUY" and self.best_bid > 0.0 and price == self.best_bid:
            ahead = float(self.bid_size)
        elif side == "SELL" and self.best_ask > 0.0 and price == self.best_ask:
            ahead = float(self.ask_size)
        else:
            ahead = 0.0

        queue = self.bid_queue if side == "BUY" else self.ask_queue
        for qo in queue:
            if qo.price == price:
                ahead += qo.remaining_qty
        return ahead

    async def _fill_market_orders(self) -> None:
        if self.best_ask > 0.0:
            for qo in list(self.market_buy):
                await self._execute_fill(qo, self.best_ask, qo.remaining_qty)
                self.market_buy.remove(qo)
        if self.best_bid > 0.0:
            for qo in list(self.market_sell):
                await self._execute_fill(qo, self.best_bid, qo.remaining_qty)
                self.market_sell.remove(qo)

    async def _fill_crossing_limits(self) -> None:
        # Fill any queued limit orders that now cross the book.
        if self.best_ask > 0.0:
            for qo in list(self.bid_queue):
                if qo.price >= self.best_ask:
                    await self._execute_fill(qo, self.best_ask, qo.remaining_qty)
                    self.bid_queue.remove(qo)
        if self.best_bid > 0.0:
            for qo in list(self.ask_queue):
                if qo.price <= self.best_bid:
                    await self._execute_fill(qo, self.best_bid, qo.remaining_qty)
                    self.ask_queue.remove(qo)

    async def _apply_trade_logger.info(
        self,
        *,
        trade_price: float,
        trade_qty: float,
        trade_side: str,
    ) -> None:
        # BUY trade consumes asks up to trade_price
        if trade_side == "BUY":
            await self._consume_queue(
                queue=self.ask_queue,
                price_cmp=lambda p: p <= trade_price,
                trade_qty=trade_qty,
                trade_price=trade_price,
                ascending=True,
            )
        # SELL trade consumes bids down to trade_price
        elif trade_side == "SELL":
            await self._consume_queue(
                queue=self.bid_queue,
                price_cmp=lambda p: p >= trade_price,
                trade_qty=trade_qty,
                trade_price=trade_price,
                ascending=False,
            )

    async def _consume_queue(
        self,
        *,
        queue: list[QueueOrder],
        price_cmp,
        trade_qty: float,
        trade_price: float,
        ascending: bool,
    ) -> None:
        # Sort by price-time priority
        queue.sort(
            key=lambda q: (q.price, q.timestamp)
            if ascending
            else (-q.price, q.timestamp)
        )

        remaining_trade = trade_qty
        for qo in list(queue):
            if not price_cmp(qo.price):
                continue

            # Deplete volume ahead first.
            if qo.volume_ahead > 0:
                deplete = min(remaining_trade, qo.volume_ahead)
                qo.volume_ahead -= deplete
                remaining_trade -= deplete
                if remaining_trade <= 0:
                    break

            # Fill the order (partial or full).
            if qo.remaining_qty > 0 and remaining_trade > 0:
                fill_qty = min(qo.remaining_qty, remaining_trade)
                await self._execute_fill(qo, trade_price, fill_qty)
                qo.remaining_qty -= fill_qty
                remaining_trade -= fill_qty

            if qo.remaining_qty <= 0:
                queue.remove(qo)

            if remaining_trade <= 0:
                break
