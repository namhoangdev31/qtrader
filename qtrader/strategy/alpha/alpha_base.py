"""Alpha base class for generating trading signals from market data."""

from abc import ABC, abstractmethod

from qtrader.core.logger import logger
from qtrader.core.types import AlphaOutput, MarketData


from qtrader.core.execution_guard import require_initialized


class AlphaBase(ABC):
    """Abstract base class for alpha generators."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = logger

    @abstractmethod
    @require_initialized
    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """Generate alpha values from market data.
        
        Args:
            market_data: Market data tick
            
        Returns:
            AlphaOutput containing generated alpha values
        """
        pass


# Use the consolidated AlphaCombiner for all operations
from qtrader.alpha.combiner import AlphaBase


# Alias for backward compatibility
Alpha = AlphaBase