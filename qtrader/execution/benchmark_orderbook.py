"""
Benchmark test for the orderbook simulator.
"""
import random
import sys
import time

from loguru import logger

sys.path.insert(0, '/home/lkct-lee-park/var/www/qtrader')
from qtrader.execution.orderbook_simulator import OrderbookSimulator


def create_test_orderbook(depth=10, base_price=100.0, spread=0.5):
    """Create a test orderbook with specified depth."""
    bids = []
    asks = []
    
    # Generate bids (descending prices)
    for i in range(depth):
        price = float(base_price - spread/2 - i * 0.1)
        size = float(random.uniform(10, 100))
        bids.append((price, size))
    
    # Generate asks (ascending prices)
    for i in range(depth):
        price = float(base_price + spread/2 + i * 0.1)
        size = float(random.uniform(10, 100))
        asks.append((price, size))
    
    return {'bids': bids, 'asks': asks}

def create_test_order(side='buy', size=None, order_type='market', price=None):
    """Create a test order."""
    if size is None:
        size = random.uniform(1, 50)
    
    order = {
        'size': size,
        'side': side,
        'type': order_type
    }
    
    if order_type == 'limit' and price is not None:
        order['price'] = price
    
    return order

def benchmark_simulator(simulator, orderbook, n_orders=1000):
    """Benchmark the simulator with n_orders."""
    # Create test orders
    orders = []
    for _ in range(n_orders):
        side = random.choice(['buy', 'sell'])
        order_type = random.choice(['market', 'limit'])
        price = None
        if order_type == 'limit':
            # Set limit price near mid-price
            best_bid = orderbook['bids'][0][0]
            best_ask = orderbook['asks'][0][0]
            mid_price = (best_bid + best_ask) / 2.0
            if side == 'buy':
                price = mid_price * random.uniform(0.99, 1.01)
            else:
                price = mid_price * random.uniform(0.99, 1.01)
        
        orders.append(create_test_order(side=side, order_type=order_type, price=price))
    
    # Benchmark
    start_time = time.perf_counter()
    fills = []
    for order in orders:
        fill = simulator.simulate_order(order, orderbook)
        fills.append(fill)
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_time_ms = (total_time / n_orders) * 1000
    
    # Statistics
    filled_orders = [f for f in fills if f['filled_size'] > 0]
    fill_rate = len(filled_orders) / n_orders if n_orders > 0 else 0
    
    avg_slippage = sum(abs(f['slippage']) for f in filled_orders) / len(filled_orders) if filled_orders else 0
    avg_fill_ratio = sum(f['fill_ratio'] for f in filled_orders) / len(filled_orders) if filled_orders else 0
    
    return {
        'total_time_s': total_time,
        'avg_time_per_order_ms': avg_time_ms,
        'orders_per_second': n_orders / total_time if total_time > 0 else 0,
        'fill_rate': fill_rate,
        'avg_slippage': avg_slippage,
        'avg_fill_ratio': avg_fill_ratio,
        'total_filled': len(filled_orders),
        'total_orders': n_orders
    }

def run_benchmarks() -> None:
    """Run various benchmark scenarios."""
    logger.info("Orderbook Simulator Benchmark")
    logger.info("=" * 50)
    
    # Test 1: Default simulator
    logger.info("\n1. Default Simulator (latency=0ms)")
    sim = OrderbookSimulator(latency_ms=0.0)
    orderbook = create_test_orderbook(depth=5, base_price=100.0, spread=0.2)
    results = benchmark_simulator(sim, orderbook, n_orders=1000)
    logger.info(f"   Avg time per order: {results['avg_time_per_order_ms']:.3f} ms")
    logger.info(f"   Orders per second: {results['orders_per_second']:.0f}")
    logger.info(f"   Fill rate: {results['fill_rate']:.1%}")
    logger.info(f"   Avg slippage: {results['avg_slippage']:.4f}")
    logger.info(f"   Meets <1ms requirement: {results['avg_time_per_order_ms'] < 1.0}")
    
    # Test 2: With latency
    logger.info("\n2. Simulator with Latency (latency=1ms)")
    sim = OrderbookSimulator(latency_ms=1.0)
    results = benchmark_simulator(sim, orderbook, n_orders=1000)
    logger.info(f"   Avg time per order: {results['avg_time_per_order_ms']:.3f} ms")
    logger.info(f"   Orders per second: {results['orders_per_second']:.0f}")
    logger.info(f"   Fill rate: {results['fill_rate']:.1%}")
    
    # Test 3: High frequency trading scenario
    logger.info("\n3. High Frequency Scenario (latency=0.1ms)")
    sim = OrderbookSimulator(latency_ms=0.1, market_impact_k=0.05, max_slippage_pct=0.005)
    results = benchmark_simulator(sim, orderbook, n_orders=1000)
    logger.info(f"   Avg time per order: {results['avg_time_per_order_ms']:.3f} ms")
    logger.info(f"   Orders per second: {results['orders_per_second']:.0f}")
    logger.info(f"   Fill rate: {results['fill_rate']:.1%}")
    logger.info(f"   Avg slippage: {results['avg_slippage']:.4f}")
    logger.info(f"   Meets <1ms requirement: {results['avg_time_per_order_ms'] < 1.0}")
    
    # Test 4: Stress test with large orders
    logger.info("\n4. Stress Test (Large Orders)")
    sim = OrderbookSimulator(latency_ms=0.0)
    # Create thin orderbook
    thin_orderbook = create_test_orderbook(depth=3, base_price=100.0, spread=0.5)
    # Create large orders
    large_orders = []
    for _ in range(100):
        side = random.choice(['buy', 'sell'])
        size = random.uniform(50, 200)  # Larger than typical liquidity
        large_orders.append(create_test_order(side=side, size=size, order_type='market'))
    
    start_time = time.perf_counter()
    fills = []
    for order in large_orders:
        fill = sim.simulate_order(order, thin_orderbook)
        fills.append(fill)
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_time_ms = (total_time / len(large_orders)) * 1000
    
    filled_orders = [f for f in fills if f['filled_size'] > 0]
    fill_rate = len(filled_orders) / len(large_orders) if large_orders else 0
    avg_slippage = sum(abs(f['slippage']) for f in filled_orders) / len(filled_orders) if filled_orders else 0
    avg_fill_ratio = sum(f['fill_ratio'] for f in filled_orders) / len(filled_orders) if filled_orders else 0
    
    logger.info(f"   Avg time per order: {avg_time_ms:.3f} ms")
    logger.info(f"   Fill rate: {fill_rate:.1%}")
    logger.info(f"   Avg slippage: {avg_slippage:.4f}")
    logger.info(f"   Avg fill ratio: {avg_fill_ratio:.1%}")
    
    # Test 5: Partial fills
    logger.info("\n5. Partial Fill Scenario")
    sim = OrderbookSimulator(latency_ms=0.0)
    # Very thin orderbook
    thin_orderbook = {
        'bids': [(99.9, 5)],  # Only 5 units at 99.9
        'asks': [(100.1, 5)]  # Only 5 units at 100.1
    }
    # Large order that will only partially fill
    large_order = create_test_order(side='buy', size=float(50), order_type='market')
    fill = sim.simulate_order(large_order, thin_orderbook)
    logger.info(f"   Order size: {large_order['size']}")
    logger.info(f"   Filled size: {fill['filled_size']}")
    logger.info(f"   Fill ratio: {fill['fill_ratio']:.1%}")
    logger.info(f"   Avg price: {fill['avg_price']:.2f}")
    logger.info("   Expected price (ask): 100.1")
    logger.info(f"   Slippage: {fill['slippage']:.4f}")

if __name__ == "__main__":
    # Set seed for reproducible results
    random.seed(42)
    run_benchmarks()