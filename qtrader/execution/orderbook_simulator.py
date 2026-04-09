from __future__ import annotations

import random

from loguru import logger


class OrderbookSimulator:
    def __init__(
        self,
        latency_ms: float = 0.0,
        market_impact_k: float = 0.1,
        max_slippage_pct: float = 0.01,
        random_seed: int | None = None,
    ) -> None:
        self.latency_ms = latency_ms
        self.market_impact_k = market_impact_k
        self.max_slippage_pct = max_slippage_pct
        self.random_seed = random_seed
        if random_seed is not None:
            random.seed(random_seed)

    def simulate_order(self, order: dict, orderbook: dict[str, list[tuple[float, float]]]) -> dict:
        size = order["size"]
        side = order["side"]
        order_type = order["type"]
        limit_price = order.get("price")
        if not orderbook.get("bids") or not orderbook.get("asks"):
            return self._create_fill_event(0, 0.0, 0.0, 0.0, side, size)
        best_bid = orderbook["bids"][0][0]
        best_ask = orderbook["asks"][0][0]
        mid_price = (best_bid + best_ask) / 2.0
        max_slippage_abs = mid_price * self.max_slippage_pct
        max_price = mid_price + max_slippage_abs
        min_price = mid_price - max_slippage_abs
        filled_size = 0.0
        total_cost = 0.0
        if side == "buy":
            book_side = orderbook["asks"]
            price_limit = limit_price if order_type == "limit" else float("inf")
            effective_limit = min(price_limit, max_price)
        else:
            book_side = orderbook["bids"]
            price_limit = limit_price if order_type == "limit" else 0.0
            effective_limit = max(price_limit, min_price)
        if not book_side:
            return self._create_fill_event(0, 0.0, 0.0, 0.0, side, size)
        for price, liquidity in book_side:
            if side == "buy":
                if price > effective_limit:
                    break
            elif price < effective_limit:
                break
            remaining = size - filled_size
            if liquidity >= remaining:
                filled_size += remaining
                total_cost += price * remaining
                break
            else:
                filled_size += liquidity
                total_cost += price * liquidity
        if filled_size > 0:
            avg_price = total_cost / filled_size
        else:
            avg_price = 0.0
        slippage = avg_price - mid_price
        fill_ratio = filled_size / size if size > 0 else 0.0
        return self._create_fill_event(filled_size, avg_price, slippage, fill_ratio, side, size)

    def _create_fill_event(
        self,
        filled_size: float,
        avg_price: float,
        slippage: float,
        fill_ratio: float,
        side: str,
        order_size: float,
    ) -> dict:
        return {
            "filled_size": filled_size,
            "avg_price": avg_price,
            "slippage": slippage,
            "fill_ratio": fill_ratio,
            "order_size": order_size,
            "side": side,
            "latency_ms": self.latency_ms,
        }


if __name__ == "__main__":
    orderbook = {
        "bids": [(100.0, 10), (99.5, 15), (99.0, 20)],
        "asks": [(101.0, 8), (101.5, 12), (102.0, 18)],
    }
    market_buy_order = {"size": 25, "side": "buy", "type": "market"}
    limit_sell_order = {"size": 20, "side": "sell", "type": "limit", "price": 100.5}
    sim = OrderbookSimulator(latency_ms=0.1, market_impact_k=0.1, max_slippage_pct=0.02)
    buy_fill = sim.simulate_order(market_buy_order, orderbook)
    sell_fill = sim.simulate_order(limit_sell_order, orderbook)
    logger.info("Market Buy Order Fill:")
    logger.info(
        f"  Filled: {buy_fill['filled_size']}/{buy_fill['order_size']} ({buy_fill['fill_ratio']:.1%})"
    )
    logger.info(f"  Avg Price: {buy_fill['avg_price']:.2f}")
    logger.info(
        f"  Slippage: {buy_fill['slippage']:.4f} ({buy_fill['slippage'] / ((orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2) * 100:.2f}% of mid)"
    )
    logger.info("\nLimit Sell Order Fill:")
    logger.info(
        f"  Filled: {sell_fill['filled_size']}/{sell_fill['order_size']} ({sell_fill['fill_ratio']:.1%})"
    )
    logger.info(f"  Avg Price: {sell_fill['avg_price']:.2f}")
    logger.info(
        f"  Slippage: {sell_fill['slippage']:.4f} ({sell_fill['slippage'] / ((orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2) * 100:.2f}% of mid)"
    )
    import time

    n_orders = 1000
    start = time.perf_counter()
    for _ in range(n_orders):
        sim.simulate_order(market_buy_order, orderbook)
    end = time.perf_counter()
    avg_time_ms = (end - start) * 1000 / n_orders
    logger.info(f"\nBenchmark: {n_orders} orders in {(end - start) * 1000:.2f}ms")
    logger.info(f"Average time per order: {avg_time_ms:.3f}ms")
    logger.info(f"Meets <1ms requirement: {avg_time_ms < 1.0}")
