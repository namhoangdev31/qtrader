from __future__ import annotations

import polars as pl
from abc import ABC, abstractmethod
from typing import Dict, List

from qtrader.core.event import FeatureEvent, MarketDataEvent


class AlphaBase(ABC):
    """Base class for all alpha feature generators."""
    
    def __init__(self, name: str, required_history: int = 20):
        """
        Initialize alpha feature generator.
        
        Args:
            name: Unique identifier for this alpha
            required_history: Minimum number of bars needed to compute feature
        """
        self.name = name
        self.required_history = required_history
        self._history: List[pl.DataFrame] = []
    
    @abstractmethod
    def compute(self, market_data: MarketDataEvent) -> pl.Series:
        """
        Compute alpha feature from market data.
        
        Args:
            market_data: Market data event containing OHLCV data
            
        Returns:
            Polars series with the alpha feature values
        """
        pass
    
    def update(self, market_data: MarketDataEvent) -> FeatureEvent | None:
        """
        Update internal state and compute feature if enough history.
        
        Args:
            market_data: Latest market data bar
            
        Returns:
            FeatureEvent if ready, None if not enough history
        """
        self._history.append(market_data.data)
        if len(self._history) > self.required_history:
            self._history.pop(0)
        
        if len(self._history) < self.required_history:
            return None
            
        # Combine history for computation
        combined_data = pl.concat(self._history)
        market_event = MarketDataEvent(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            data=combined_data
        )
        
        feature_series = self.compute(market_event)
        return FeatureEvent(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            features={self.name: feature_series}
        )
    
    def reset(self) -> None:
        """Reset internal state."""
        self._history.clear()


# Alias for compatibility
Alpha = AlphaBase


class AlphaCombiner:
    """Combines multiple alpha generators into a single feature set."""
    
    def __init__(self, alphas: List[AlphaBase]):
        self.alphas = {alpha.name: alpha for alpha in alphas}
    
    def update(self, market_data: MarketDataEvent) -> FeatureEvent | None:
        """
        Update all alpha generators and combine their outputs.
        
        Args:
            market_data: Latest market data bar
            
        Returns:
            Combined FeatureEvent or None if any alpha not ready
        """
        features = {}
        ready_alphas = 0
        
        for alpha in self.alphas.values():
            feature_event = alpha.update(market_data)
            if feature_event is None:
                return None  # Not ready yet
            features.update(feature_event.features)
            ready_alphas += 1
        
        if ready_alphas == len(self.alphas):
            return FeatureEvent(
                symbol=market_data.symbol,
                timestamp=market_data.timestamp,
                features=features
            )
        return None
    
    def reset(self) -> None:
        """Reset all alpha generators."""
        for alpha in self.alphas.values():
            alpha.reset()