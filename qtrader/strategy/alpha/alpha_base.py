"""Alpha base class for generating trading signals from market data."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from qtrader.core.types import MarketData, AlphaOutput
from qtrader.core.logger import logger


class AlphaBase(ABC):
    """Abstract base class for alpha generators."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logger

    @abstractmethod
    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """Generate alpha values from market data.
        
        Args:
            market_data: Market data tick
            
        Returns:
            AlphaOutput containing generated alpha values
        """
        pass


class AlphaCombiner:
    """Combines multiple alpha generators into a single output."""

    def __init__(self, alpha_generators: list[AlphaBase]):
        self.alpha_generators = alpha_generators
        self.logger = logger

    async def combine(self, market_data: MarketData) -> AlphaOutput:
        """Combine outputs from multiple alpha generators.
        
        Args:
            market_data: Market data tick
            
        Returns:
            Combined AlphaOutput
        """
        combined_alphas = {}
        
        for alpha_gen in self.alpha_generators:
            try:
                alpha_output = await alpha_gen.generate(market_data)
                # Prefix alpha names with generator name to avoid collisions
                for alpha_name, alpha_value in alpha_output.alpha_values.items():
                    combined_key = f"{alpha_gen.name}_{alpha_name}"
                    combined_alphas[combined_key] = alpha_value
            except Exception as e:
                self.logger.error(
                    f"Error generating alpha from {alpha_gen.name}: {e}",
                    exc_info=True
                )
                # Continue with other generators
        
        return AlphaOutput(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            alpha_values=combined_alphas,
            metadata={"combiner": "AlphaCombiner", "generator_count": len(self.alpha_generators)}
        )


# Alias for backward compatibility
Alpha = AlphaBase