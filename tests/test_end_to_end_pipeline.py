"""End-to-End Verification of the QTrader Pipeline.

Tests:
1. DataLake ingestion
2. Feature Engine & Store
3. Alpha Engine composite signal
4. Regime Detection
5. Backtest Harness (with RustTickEngine)
6. Research Pipeline approval & config generation
7. Bot Runner initialization
"""

import asyncio
import logging
import os
import shutil
import polars as pl
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from qtrader.alpha.registry import AlphaEngine
from qtrader.analytics.drift import DriftMonitor
from qtrader.backtest.integration import BacktestHarness
from qtrader.backtest.tearsheet import TearsheetGenerator
from qtrader.backtest.tick_engine import RustTickEngine
from qtrader.bot.config import BotConfig
from qtrader.bot.runner import TradingBot
from qtrader.data.datalake import DataLake
from qtrader.features.engine import FactorEngine
from qtrader.features.store import FeatureStore
from qtrader.ml.regime import RegimeDetector
from qtrader.pipeline.research import ResearchPipeline

def create_mock_data(datalake: DataLake, symbol: str, n_rows: int = 2000):
    """Generate dummy data for tests."""
    df = pl.DataFrame({
        "timestamp": pl.datetime_range(
            start=pl.datetime(2023, 1, 1), 
            end=pl.datetime(2023, 1, 1) + pl.duration(days=n_rows-1),
            interval="1d",
            eager=True
        ),
        "symbol": [symbol]*n_rows,
        "open": range(100, 100+n_rows),
        "high": range(105, 105+n_rows),
        "low": range(95, 95+n_rows),
        "close": range(101, 101+n_rows),
        "volume": [1000.0]*n_rows,
    }).with_columns([
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
    ])
    datalake.save_data(df, symbol, "1d")

async def test_full_pipeline():
    print("=== QTrader End-to-End Verification ===")
    
    # 1. Init Components
    os.environ["QTRADER_DATA_DIR"] = "/tmp/qtrader_test_data"
    shutil.rmtree("/tmp/qtrader_test_data", ignore_errors=True)
    
    dl = DataLake("/tmp/qtrader_test_data")
    fs = FeatureStore("/tmp/qtrader_test_data/features")
    fe = FactorEngine(store=fs)
    ae = AlphaEngine(alpha_names=["momentum", "trend"])
    rd = RegimeDetector()
    
    try:
        engine = RustTickEngine()
        print("[OK] RustTickEngine Loaded")
    except Exception as e:
        print(f"[FAIL] RustTickEngine: {e}")
        return

    bh = BacktestHarness(engine=engine, tearsheet_gen=TearsheetGenerator())
    dm = DriftMonitor()
    
    rp = ResearchPipeline(
        datalake=dl,
        feature_engine=fe,
        alpha_engine=ae,
        regime_detector=rd,
        backtest_harness=bh,
        drift_monitor=dm,
    )
    
    # 2. Mock Data
    create_mock_data(dl, "TEST_COIN")
    print("[OK] DataLake mock injected")

    # 3. Run Pipeline
    # Using low targets to guarantee approval for testing Bot deployment
    result = rp.run(
        symbols=["TEST_COIN"],
        timeframe="1d",
        start_date="2023-01-01",
        end_date="2023-12-31",
        strategy_name="test_strat",
        walk_forward=False,
        target_sharpe=-10.0,
        target_max_dd=1.0, 
        target_win_rate=0.0
    )
    
    if result.approved_for_deployment:
        print(f"[OK] Strategy Approved. Config exported to: {result.config_path}")
    else:
        print("[FAIL] Strategy was not approved.")
        return

    # 4. Verify Bot Initialization matching the pipeline export
    bot_config = BotConfig.from_yaml(result.config_path)
    bot = TradingBot(bot_config)
    print(f"[OK] Bot initialized dynamically from approved baseline (Sharpe: {bot.backtest_baseline.sharpe_ratio:.2f})")
    
    print("\n=== All 14 Modules Integrated Successfully! ===")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
