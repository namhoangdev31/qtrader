import polars as pl
import asyncio
from qtrader.data.datalake import DataLake
from qtrader.data.duckdb_client import DuckDBClient
from qtrader.features.store import FeatureStore
from qtrader.features.engine import FactorEngine
from qtrader.features.factors.price import PriceMomentum, RollingVolatility
from qtrader.features.factors.volume import VolumeZScore
from scripts.generate_test_data import generate_synthetic_data

async def verify_v2_foundation():
    print("🚀 Verifying QTrader v2 Data Foundation...")
    
    # 1. Setup DataLake and DuckDB
    dl = DataLake(base_path="qtrader/data/datalake_test")
    client = DuckDBClient(datalake_path="qtrader/data/datalake_test")
    
    # 2. Generate and Save Raw Data
    df = generate_synthetic_data("BTCUSDT", days=2) # Hourly data
    dl.save_data(df, "BTCUSDT", "1h")
    print("✅ Raw data saved to DataLake")
    
    # 3. Query via DuckDB
    res = client.query_datalake("BTCUSDT", "1h", filter_sql="close > 100")
    print(f"✅ DuckDB Query result size: {len(res)}")
    
    # 4. Compute Features via FactorEngine
    store = FeatureStore(base_path="qtrader/data/feature_store_test")
    engine = FactorEngine(store)
    engine.register_factor(PriceMomentum(20))
    engine.register_factor(RollingVolatility(20))
    engine.register_factor(VolumeZScore(20))
    
    raw_df = dl.load_data("BTCUSDT", "1h")
    features_df = engine.compute_and_save(raw_df, "BTCUSDT", "1h")
    print(f"✅ Computed {len(engine.factors)} factors. Feature set shape: {features_df.shape}")
    
    # 5. Load from FeatureStore
    loaded_features = store.load_features("BTCUSDT", "1h")
    print(f"✅ Loaded features from Store. Columns: {loaded_features.columns}")
    
    print("\n🌟 QTrader v2 High-Performance Data Foundation is VERIFIED!")

if __name__ == "__main__":
    asyncio.run(verify_v2_foundation())
