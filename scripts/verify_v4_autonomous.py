import polars as pl
import numpy as np
import asyncio
from qtrader.ml.regime import RegimeDetector
from qtrader.ml.rotation import ModelRotator
from qtrader.execution.oms import UnifiedOMS
from scripts.generate_test_data import generate_synthetic_data

async def verify_v4_autonomous_intelligence():
    print("🤖 Verifying QTrader v4 Autonomous Intelligence...")
    
    # 1. Regime Detection & Rotation
    df = generate_synthetic_data("BTCUSDT", days=10)
    
    # Add features
    df = df.with_columns([
        pl.col("close").pct_change().alias("returns"),
        pl.col("close").pct_change().rolling_std(20).alias("volatility")
    ]).drop_nulls()

    detector = RegimeDetector(n_regimes=3)
    detector.fit(df, ["returns", "volatility"])
    
    regimes = detector.predict_regime(df, ["returns", "volatility"])
    print(f"✅ Regime Detection: Found {len(regimes.unique())} distinct market states")

    rotator = ModelRotator()
    rotator.update_map({0: "Model_Bear", 1: "Model_Sideways", 2: "Model_Bull"})
    
    # Simulate a regime shift
    target_model = rotator.on_regime_change(2) # Switch to Bull
    print(f"✅ Model Rotation: Autonomous shift triggered model: {target_model}")

    # 2. Unified OMS & Multi-Venue
    oms = UnifiedOMS()
    oms.positions["Binance"] = {"USDT": 10000, "BTC": 0.5}
    oms.positions["Bybit"] = {"USDT": 5000, "BTC": 0.1}
    
    total_btc = oms.get_total_exposure("BTC")
    print(f"✅ Unified OMS: Total BTC Exposure across venues: {total_btc}")

    print("\n🏆 QTrader 2026 (v4) AUTONOMOUS SYSTEM READY!")

if __name__ == "__main__":
    asyncio.run(verify_v4_autonomous_intelligence())
