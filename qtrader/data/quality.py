from typing import Any

import polars as pl


class DataQualityChecker:
    """Institutional-grade data validation and cleaning."""

    @staticmethod
    def check_anomalies(df: pl.DataFrame) -> dict[str, Any]:
        """Runs a series of checks for bad data."""
        results = {}
        
        # 1. Monotonic timestamps
        is_monotonic = df["timestamp"].is_sorted()
        results["monotonic_timestamps"] = is_monotonic
        
        # 2. Duplicate timestamps
        duplicates = df["timestamp"].is_duplicated().sum()
        results["duplicate_timestamps"] = duplicates

        # 3. Large price jumps (e.g., > 10% in one bar)
        if "close" in df.columns:
            returns = df["close"].pct_change().abs()
            price_jumps = (returns > 0.1).sum()
            results["price_jumps_count"] = price_jumps

        # 4. Volume anomalies (e.g., negative or zero)
        if "volume" in df.columns:
            negative_vol = (df["volume"] < 0).sum()
            zero_vol = (df["volume"] == 0).sum()
            results["negative_volume"] = negative_vol
            results["zero_volume"] = zero_vol

        # 5. Missing values
        results["missing_values"] = df.null_count().to_dicts()[0]

        return results

    @staticmethod
    def fill_gaps(df: pl.DataFrame, freq: str = "1h") -> pl.DataFrame:
        """Fills missing timestamps and interpolates values."""
        if "timestamp" not in df.columns:
            return df
            
        # Create a complete range of timestamps
        start = df["timestamp"].min()
        end = df["timestamp"].max()
        
        full_range = pl.datetime_range(start, end, interval=freq, eager=True).to_frame("timestamp")
        
        # Join with original data
        df_full = full_range.join(df, on="timestamp", how="left")
        
        # Interpolate numeric columns
        numeric_cols = [c for c, t in df.schema.items() if t.is_numeric() and c != "timestamp"]
        df_full = df_full.with_columns([
            pl.col(c).interpolate() for c in numeric_cols
        ])
        
        return df_full

    @staticmethod
    def clean_data(df: pl.DataFrame) -> pl.DataFrame:
        """Applies standard cleaning procedures."""
        # Remove duplicates
        df = df.unique(subset=["timestamp"], keep="first")
        
        # Ensure sorting
        df = df.sort("timestamp")
        
        return df

class AdjustmentEngine:
    """Handles stock splits and dividends (Corporate Actions)."""
    
    @staticmethod
    def apply_split(df: pl.DataFrame, ratio: float) -> pl.DataFrame:
        """Adjusts historical prices for a split."""
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if col in df.columns:
                df = df.with_columns(pl.col(col) / ratio)
        
        if "volume" in df.columns:
            df = df.with_columns(pl.col("volume") * ratio)
            
        return df
