"""Test Rust-based Tick Execution Simulator."""

import polars as pl
import numpy as np

try:
    from qtrader.backtest.tick_engine import RustTickEngine, TickEngineConfig
except ImportError as e:
    print(f"Skipping tests: {e}")
    RustTickEngine = None


def test_rust_simulator_basic():
    if not RustTickEngine:
        return

    print("Running Rust Tick Simulator Test...")

    # 1. Create Mock Data
    n_bars = 1000
    timestamps = np.array([1700000000000 + i * 1000 for i in range(n_bars)], dtype=np.int64)
    closes = np.array([100.0 + (i * 0.1) for i in range(n_bars)], dtype=np.float64)
    
    # Simple strategy: Buy at tick 10, Sell at tick 500
    signals = np.zeros(n_bars, dtype=np.float64)
    signals[10] = 1.0
    signals[500] = -1.0

    df = pl.DataFrame({
        "timestamp": timestamps,
        "close": closes,
        "signal": signals,
    })

    # 2. Run Engine
    config = TickEngineConfig(
        initial_capital=100_000.0,
        latency_ms=10,
        fee_rate=0.0005,
        slippage_bps=1.0, 
    )
    engine = RustTickEngine(config)
    
    result = engine.run(df, signal_col="signal", symbol="TEST_COIN")
    
    # 3. Assertions
    eq_curve = result["equity_curve"]
    final_eq = result["final_equity"]

    print(f"Initial Equity: {config.initial_capital}")
    print(f"Final Equity  : {final_eq}")
    print(f"Equity Curve length: {len(eq_curve)}")

    assert len(eq_curve) == n_bars, "Equity curve should match input length"
    assert final_eq > 0.0, "Should have positive equity"

if __name__ == "__main__":
    test_rust_simulator_basic()
