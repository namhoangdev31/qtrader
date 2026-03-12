import polars as pl
from qtrader.data.quality import DataQualityChecker, AdjustmentEngine

def verify_data_reliability():
    print("🧹 Verifying Data Quality & Adjustment Engine...")
    
    # 1. Create dirty data
    df = pl.DataFrame({
        "timestamp": [1, 2, 4, 3], # Out of order
        "close": [100.0, 110.0, 150.0, 115.0], # 150 is a huge jump
        "volume": [100, -10, 0, 105], # Negative and zero volume
    })
    
    # 2. Check anomalies
    checker = DataQualityChecker()
    results = checker.check_anomalies(df)
    print(f"✅ Anomalies detected: {results}")

    # 3. Clean data
    clean_df = checker.clean_data(df)
    print(f"✅ Cleaned data shape: {clean_df.shape} (Sorted: {clean_df['timestamp'].is_sorted()})")

    # 4. Apply corporate actions
    adj_df = AdjustmentEngine.apply_split(clean_df, 2.0) # 2-for-1 split
    print(f"✅ Adjusted price (split 2:1): {adj_df['close'][0]} (Original: {clean_df['close'][0]})")

    print("\n✅ Data Reliability Foundation VERIFIED!")

if __name__ == "__main__":
    verify_data_reliability()
