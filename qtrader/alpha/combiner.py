from __future__ import annotations

import polars as pl
from typing import List, Dict, Optional

from qtrader.strategy.alpha_base import AlphaBase


class AlphaCombiner:
    """
    Combines multiple alpha factors into a single feature set.
    """

    def __init__(self, alphas: List[AlphaBase]):
        """
        Initialize the alpha combiner.

        Args:
            alphas: List of alpha factor instances.
        """
        self.alphas = alphas
        # We assume each alpha has a name attribute; if not, we use the class name.
        self.alpha_names = [getattr(alpha, 'name', alpha.__class__.__name__) for alpha in alphas]

    def update(self, market_data: pl.DataFrame) -> Optional[Dict[str, pl.Series]]:
        """
        Update all alpha factors with the latest market data and combine their outputs.

        Args:
            market_data: DataFrame containing OHLCV data for the latest bar(s).

        Returns:
            A dictionary mapping alpha names to their feature series, or None if any alpha
            is not ready (i.e., not enough history).
        """
        features = {}
        for alpha, name in zip(self.alphas, self.alpha_names):
            try:
                # The alpha's compute method expects a DataFrame and returns a Series.
                feature_series = alpha.compute(market_data)
                # Validate the output: must be a Series of Float64 and same length as market_data.
                if not isinstance(feature_series, pl.Series):
                    raise TypeError(f"Alpha {name} did not return a pl.Series")
                if feature_series.len() != len(market_data):
                    raise ValueError(f"Alpha {name} output length mismatch")
                if feature_series.dtype != pl.Float64:
                    raise TypeError(f"Alpha {name} output dtype is {feature_series.dtype}, expected Float64")
                features[name] = feature_series
            except Exception as e:
                # If any alpha fails, we return None to indicate not ready.
                # In a production system, we might want to log and continue with a fallback.
                return None
        return features

    def reset(self) -> None:
        """Reset all alpha factors."""
        for alpha in self.alphas:
            if hasattr(alpha, 'reset'):
                alpha.reset()