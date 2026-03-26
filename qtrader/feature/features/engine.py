"""Factor engine for batch and incremental feature computation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from qtrader.feature.features.base import Feature
    from qtrader.feature.features.store import FeatureStore

__all__ = ["FactorEngine"]


class FactorEngine:
    """Orchestrates batch computation and storage of features."""

    def __init__(self, store: FeatureStore) -> None:
        self.store = store
        self.factors: list[Feature] = []

    def register_factor(self, factor: Feature) -> None:
        """Adds a factor to the engine."""
        self.factors.append(factor)

    def get_all_feature_names(self) -> list[str]:
        """Return names of all registered factors (for pipeline and bot)."""
        return [getattr(f, "name", f"factor_{i}") for i, f in enumerate(self.factors)]

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute all registered factors on df without saving to store."""
        feature_dfs: list[pl.DataFrame] = []
        for factor in self.factors:
            result = factor.compute(df)
            if isinstance(result, pl.Series):
                feature_dfs.append(result.to_frame())
            else:
                feature_dfs.append(result)
        if not feature_dfs:
            return pl.DataFrame()
        final = pl.concat(feature_dfs, how="horizontal")
        if "timestamp" in df.columns:
            final = pl.concat([df.select("timestamp"), final], how="horizontal")
        return final

    def compute_latest(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute features and return only the last row (for live signal loop)."""
        full = self.compute(df)
        if full.is_empty():
            return full
        return full.tail(1)

    def compute_and_save(self, df: pl.DataFrame, symbol: str, timeframe: str) -> pl.DataFrame:
        """Computes all registered factors and saves to store."""
        final_features = self.compute(df)
        if not final_features.is_empty():
            self.store.save_features(final_features, symbol, timeframe)
        return final_features

    def compute_multi_symbol(self, raw_dfs: dict[str, pl.DataFrame], timeframe: str) -> pl.DataFrame:
        """Compute features for multiple symbols and combine with a symbol column."""
        features_list = []
        for symbol, df in raw_dfs.items():
            features = self.compute(df)
            if not features.is_empty():
                features = features.with_columns(pl.lit(symbol).alias("symbol"))
                features_list.append(features)
        if not features_list:
            return pl.DataFrame()
        return pl.concat(features_list, how="vertical")
