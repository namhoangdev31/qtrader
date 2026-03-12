import polars as pl
from typing import List, Dict, Type
from qtrader.features.base import Feature
from qtrader.features.store import FeatureStore

class FactorEngine:
    """Orchestrates batch computation and storage of features."""
    
    def __init__(self, store: FeatureStore) -> None:
        self.store = store
        self.factors: List[Feature] = []

    def register_factor(self, factor: Feature) -> None:
        """Adds a factor to the engine."""
        self.factors.append(factor)

    def compute_and_save(self, df: pl.DataFrame, symbol: str, timeframe: str) -> pl.DataFrame:
        """Computes all registered factors and saves to store."""
        feature_dfs = []
        for factor in self.factors:
            # Each compute call returns a Series or DataFrame
            result = factor.compute(df)
            if isinstance(result, pl.Series):
                feature_dfs.append(result.to_frame())
            else:
                feature_dfs.append(result)

        # Horizontal concat of features
        if not feature_dfs:
            return pl.DataFrame()
            
        final_features = pl.concat(feature_dfs, how="horizontal")
        
        # Merge with timestamp from original df to keep it aligned
        if "timestamp" in df.columns:
            final_features = pl.concat([df.select("timestamp"), final_features], how="horizontal")
            
        self.store.save_features(final_features, symbol, timeframe)
        return final_features
