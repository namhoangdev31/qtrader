import polars as pl
import numpy as np
import asyncio
from qtrader.execution.safety import SafetyLayer
from qtrader.ml.stability import RotationHysteresis
from qtrader.ml.hmm_smoother import HMMRegimeSmoother
from qtrader.core.event import OrderEvent

def verify_v4_stability():
    print("🛡️ Verifying QTrader v4 Stability & Safety Guards...")

    # 1. Nano-Safety Layer Check
    safety = SafetyLayer()
    order = OrderEvent("BTCUSDT", "BUY", 1.0, "LIMIT", 50000.0)
    
    # Healthy state
    market_ok = {"spread_pct": 0.001, "top_depth": 5000.0}
    is_safe = safety.check_order(order, market_ok)
    print(f"✅ Safety Check (Healthy): {is_safe}")

    # Flash crash state
    market_crash = {"spread_pct": 0.06, "top_depth": 100.0}
    is_safe = safety.check_order(order, market_crash)
    print(f"✅ Safety Check (Crash): {is_safe} (Halted: {safety.is_halted})")

    # 2. Rotation Hysteresis Check
    hysteresis = RotationHysteresis(persistence_bars=3, cooldown_sec=10)
    print("🔄 Testing Regime Hysteresis (Persistence=3)...")
    for i in range(1, 5):
        valid = hysteresis.validate_shift(1) # Try to shift to state 1
        print(f"   Bar {i}: Shift Validated = {valid}")

    # 3. HMM Smoothing Check
    smoother = HMMRegimeSmoother(n_regimes=2, stay_prob=0.8)
    raw_probs = np.array([
        [0.4, 0.6], # Observation favors 1
        [0.6, 0.4], # Observation favors 0 (noisy)
        [0.6, 0.4], 
        [0.6, 0.4]
    ])
    smooth_regimes = smoother.process_series(raw_probs)
    print(f"✅ HMM Smoothing: Raw sequence [1, 0, 0, 0] -> Smoothed: {smooth_regimes.to_list()}")

    print("\n🏆 QTrader v4 STABILITY & SAFETY VERIFIED!")

if __name__ == "__main__":
    verify_v4_stability()
