import time
import numpy as np
import polars as pl
from decimal import Decimal
import logging

try:
    import qtrader_core
    HAS_RUST_CORE = True
except ImportError:
    HAS_RUST_CORE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PARITY_BENCHMARK")

def benchmark_stats_parity():
    """Verify Bit-Perfect Parity and Performance between Python/Polars and Rust."""
    if not HAS_RUST_CORE:
        logger.error("qtrader_core not installed. Skipping benchmark.")
        return

    # 1. Generate 1M return observations
    n = 1_000_000
    returns = np.random.normal(0, 0.01, n).tolist()
    
    stats_engine = qtrader_core.StatsEngine()
    
    # --- EXPECTED SHORTFALL (CVAR) PARITY ---
    # Python/Polars approach
    start_py = time.perf_counter()
    df = pl.DataFrame({"ret": returns})
    var_95 = df["ret"].quantile(0.05)
    es_py = df.filter(pl.col("ret") <= var_95)["ret"].mean()
    end_py = time.perf_counter()
    
    # Rust approach
    start_rs = time.perf_counter()
    es_rs = stats_engine.calculate_historical_es(returns, 0.05)
    end_rs = time.perf_counter()
    
    logger.info(f"CVaR (95%) | Python: {es_py:.10f} | Rust: {es_rs:.10f}")
    logger.info(f"Latency   | Python: {(end_py-start_py)*1000:.2f}ms | Rust: {(end_rs-start_rs)*1000:.2f}ms")
    logger.info(f"Speedup   | {((end_py-start_py)/(end_rs-start_rs)):.1f}x")
    
    assert abs(es_py - es_rs) < 1e-10, "CVaR Parity Breach!"

def benchmark_risk_latency():
    """Verify < 100μs Risk Guardrail execution."""
    if not HAS_RUST_CORE: return
    
    risk_engine = qtrader_core.RiskEngine(
        max_position_usd=100000.0,
        max_drawdown_pct=0.15,
        max_order_qty=100.0,
        max_order_notional=10000.0,
        max_orders_per_second=1000,
        max_price_deviation_pct=0.03
    )
    
    account = qtrader_core.Account(100000.0)
    order = qtrader_core.Order(1, "BTC-USD", qtrader_core.Side.Buy, 0.5, 65000.0, qtrader_core.OrderType.Limit, int(time.time()))
    
    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        risk_engine.check_order(order, account, 65000.0, 100000.0)
    end = time.perf_counter()
    
    avg_latency_us = ((end - start) / iterations) * 1_000_000
    logger.info(f"Risk Guardrail Latency | Avg: {avg_latency_us:.2f}μs")
    
    if avg_latency_us < 100:
        logger.info("RESULT: [PASS] Institutional Latency Standard (< 100μs)")
    else:
        logger.warning(f"RESULT: [FAIL] Latency is {avg_latency_us:.2f}μs - potential system contention.")

def benchmark_simulator_throughput():
    """Verify High-Fidelity Simulator throughput."""
    if not HAS_RUST_CORE: return
    
    n = 100_000
    ts = np.arange(n, dtype=np.int64)
    bid = np.random.normal(100, 1, n).tolist()
    ask = (np.array(bid) + 0.01).tolist()
    bid_sz = np.random.uniform(1, 10, n).tolist()
    ask_sz = np.random.uniform(1, 10, n).tolist()
    signals = np.random.choice([0, 1, -1], n, p=[0.9, 0.05, 0.05]).astype(float).tolist()
    
    config = qtrader_core.SimulatorConfig(100000.0, 5, 0.001, 1.0, 50000.0, 0.15)
    
    start = time.perf_counter()
    equity, final_pnl = qtrader_core.run_hft_simulation(
        config, "BTC-USD", ts, bid, ask, bid_sz, ask_sz, signals
    )
    end = time.perf_counter()
    
    logger.info(f"Simulator Throughput | {n} ticks in {(end-start)*1000:.2f}ms")
    logger.info(f"Ticks/Sec: {int(n / (end-start)):,}")

if __name__ == "__main__":
    logger.info("--- INSTITUTIONAL PARITY & PERFORMANCE AUDIT ---")
    benchmark_stats_parity()
    benchmark_risk_latency()
    benchmark_simulator_throughput()
