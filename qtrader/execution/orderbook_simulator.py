"""
Orderbook simulator for modeling execution slippage and market impact.
"""
from __future__ import annotations

import random

from loguru import logger


class OrderbookSimulator:
    """
    Simulates order execution against an orderbook snapshot.
    
    Models:
    - Orderbook walking (consuming liquidity)
    - Slippage calculation
    - Market impact via book walk
    - Latency simulation (configurable delay)
    - Order types: market, limit
    - Partial fills
    - Slippage capping to avoid extreme execution prices
    """
    
    def __init__(
        self,
        latency_ms: float = 0.0,
        market_impact_k: float = 0.1,
        max_slippage_pct: float = 0.01,
        random_seed: int | None = None
    ) -> None:
        """
        Initialize the orderbook simulator.
        
        Args:
            latency_ms: Fixed latency to simulate (in milliseconds)
            market_impact_k: Factor for market impact model (impact = k * (order_size / total_liquidity))
            max_slippage_pct: Maximum allowed slippage as percentage of mid-price
            random_seed: Seed for reproducible randomness in stress testing
        """
        self.latency_ms = latency_ms
        self.market_impact_k = market_impact_k
        self.max_slippage_pct = max_slippage_pct
        self.random_seed = random_seed
        if random_seed is not None:
            random.seed(random_seed)
    
    def simulate_order(
        self, 
        order: dict, 
        orderbook: dict[str, list[tuple[float, float]]]
    ) -> dict:
        """
        Simulate order execution against an orderbook snapshot.
        
        Args:
            order: Dict with keys:
                - 'size': float (positive order size)
                - 'side': 'buy' or 'sell'
                - 'type': 'market' or 'limit'
                - 'price': float (limit price, required for limit orders)
            orderbook: Dict with:
                - 'bids': List of (price, size) tuples, sorted descending by price (best bid first)
                - 'asks': List of (price, size) tuples, sorted ascending by price (best ask first)
                
        Returns:
            Dict representing fill event with:
                - 'avg_price': Volume-weighted average fill price
                - 'slippage': avg_price - mid_price (positive for buy slippage, negative for sell slippage)
                - 'fill_ratio': fraction of order that was filled (0.0 to 1.0)
                - 'filled_size': actual size filled
                - 'order_size': original order size
                - 'side': order side
                - 'latency_ms': simulated latency
        """
        # Extract order parameters
        size = order['size']
        side = order['side']
        order_type = order['type']
        limit_price = order.get('price')  # None for market orders
        
        # Handle empty orderbook
        if not orderbook.get('bids') or not orderbook.get('asks'):
            return self._create_fill_event(0, 0.0, 0.0, 0.0, side, size)
        
        # Calculate mid-price from best bid and ask
        best_bid = orderbook['bids'][0][0]
        best_ask = orderbook['asks'][0][0]
        mid_price = (best_bid + best_ask) / 2.0
        
        # Calculate price limits based on slippage constraints
        max_slippage_abs = mid_price * self.max_slippage_pct
        max_price = mid_price + max_slippage_abs   # maximum price we'll pay for a buy
        min_price = mid_price - max_slippage_abs   # minimum price we'll accept for a sell
        
        # Initialize tracking variables
        filled_size = 0.0
        total_cost = 0.0  # for buys: cash spent, for sells: cash received
        
        # Determine which side of the book to walk and effective price limits
        if side == 'buy':
            book_side = orderbook['asks']  # we consume asks when buying
            # For buys: limit price is maximum we're willing to pay
            # Market order: no limit (infinity) but capped by max_slippage
            # Limit order: must be <= limit_price and <= max_price
            price_limit = limit_price if order_type == 'limit' else float('inf')
            effective_limit = min(price_limit, max_price)
        else:  # sell
            book_side = orderbook['bids']  # we consume bids when selling
            # For sells: limit price is minimum we're willing to accept
            # Market order: no limit (zero) but floored by min_slippage
            # Limit order: must be >= limit_price and >= min_price
            price_limit = limit_price if order_type == 'limit' else 0.0
            effective_limit = max(price_limit, min_price)
        
        # If the book side we need to walk is empty, we cannot fill
        if not book_side:
            return self._create_fill_event(0, 0.0, 0.0, 0.0, side, size)
        
        # Walk the book to simulate execution
        for price, liquidity in book_side:
            # Check if we can trade at this price given our constraints
            if side == 'buy':
                if price > effective_limit:
                    break  # price too high, stop walking
            elif price < effective_limit:
                break  # price too low, stop walking
            
            # Calculate how much we can fill at this price level
            remaining = size - filled_size
            if liquidity >= remaining:
                # Fill the remainder of our order at this level
                filled_size += remaining
                total_cost += price * remaining
                break  # order completely filled
            else:
                # Take all liquidity at this level
                filled_size += liquidity
                total_cost += price * liquidity
                # Continue to next level (order may be partially filled)
        
        # Calculate average price and slippage
        if filled_size > 0:
            avg_price = total_cost / filled_size
        else:
            avg_price = 0.0  # no fill
        
        slippage = avg_price - mid_price
        fill_ratio = filled_size / size if size > 0 else 0.0
        
        return self._create_fill_event(
            filled_size, avg_price, slippage, fill_ratio, side, size
        )
    
    def _create_fill_event(
        self, 
        filled_size: float, 
        avg_price: float, 
        slippage: float, 
        fill_ratio: float, 
        side: str, 
        order_size: float
    ) -> dict:
        """Helper to create a fill event dictionary."""
        return {
            'filled_size': filled_size,
            'avg_price': avg_price,
            'slippage': slippage,
            'fill_ratio': fill_ratio,
            'order_size': order_size,
            'side': side,
            'latency_ms': self.latency_ms
        }


# Example usage and simple benchmark
if __name__ == "__main__":
    # Example orderbook
    orderbook = {
        'bids': [(100.0, 10), (99.5, 15), (99.0, 20)],  # descending prices
        'asks': [(101.0, 8), (101.5, 12), (102.0, 18)]   # ascending prices
    }
    
    # Example market buy order
    market_buy_order = {
        'size': 25,
        'side': 'buy',
        'type': 'market'
    }
    
    # Example limit sell order
    limit_sell_order = {
        'size': 20,
        'side': 'sell',
        'type': 'limit',
        'price': 100.5
    }
    
    # Create simulator
    sim = OrderbookSimulator(latency_ms=0.1, market_impact_k=0.1, max_slippage_pct=0.02)
    
    # Simulate orders
    buy_fill = sim.simulate_order(market_buy_order, orderbook)
    sell_fill = sim.simulate_order(limit_sell_order, orderbook)
    
    logger.info("Market Buy Order Fill:")
    logger.info(f"  Filled: {buy_fill['filled_size']}/{buy_fill['order_size']} ({buy_fill['fill_ratio']:.1%})")
    logger.info(f"  Avg Price: {buy_fill['avg_price']:.2f}")
    logger.info(f"  Slippage: {buy_fill['slippage']:.4f} ({(buy_fill['slippage']/((orderbook['bids'][0][0]+orderbook['asks'][0][0])/2))*100:.2f}% of mid)")
    
    logger.info("\nLimit Sell Order Fill:")
    logger.info(f"  Filled: {sell_fill['filled_size']}/{sell_fill['order_size']} ({sell_fill['fill_ratio']:.1%})")
    logger.info(f"  Avg Price: {sell_fill['avg_price']:.2f}")
    logger.info(f"  Slippage: {sell_fill['slippage']:.4f} ({(sell_fill['slippage']/((orderbook['bids'][0][0]+orderbook['asks'][0][0])/2))*100:.2f}% of mid)")
    
    # Simple benchmark: time 1000 orders
    import time
    n_orders = 1000
    start = time.perf_counter()
    for _ in range(n_orders):
        sim.simulate_order(market_buy_order, orderbook)
    end = time.perf_counter()
    avg_time_ms = (end - start) * 1000 / n_orders
    logger.info(f"\nBenchmark: {n_orders} orders in {(end-start)*1000:.2f}ms")
    logger.info(f"Average time per order: {avg_time_ms:.3f}ms")
    logger.info(f"Meets <1ms requirement: {avg_time_ms < 1.0}")