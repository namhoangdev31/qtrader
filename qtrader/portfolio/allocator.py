"""Portfolio allocation base class."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from qtrader.core.types import SignalEvent, AllocationWeights
from qtrader.core.logger import logger


class AllocatorBase(ABC):
    """Abstract base class for portfolio allocators."""

    def __init__(self, name: str = "AllocatorBase"):
        self.name = name
        self.logger = logger
        self._risk_multiplier = Decimal('1.0')  # Default risk multiplier

    @abstractmethod
    async def allocate(self, signal_event: SignalEvent) -> AllocationWeights:
        """Calculate portfolio allocation weights based on trading signal.
         
        Args:
            signal_event: Trading signal from strategy
             
        Returns:
            AllocationWeights containing portfolio weights
        """
        pass

    def set_risk_multiplier(self, multiplier: Decimal) -> None:
        """Set the risk multiplier for position sizing.
        
        Args:
            multiplier: Risk multiplier to apply (e.g., 0.5 for half risk, 2.0 for double risk)
        """
        self._risk_multiplier = max(Decimal('0.0'), multiplier)  # Ensure non-negative
        self.logger.debug(f"Risk multiplier set to {self._risk_multiplier}")

    def get_risk_multiplier(self) -> Decimal:
        """Get the current risk multiplier.
        
        Returns:
            Current risk multiplier
        """
        return self._risk_multiplier


# Simple implementation that allocates based on signal strength
class SimpleAllocator(AllocatorBase):
    """Simple allocator that allocates based on signal strength."""

    def __init__(self, name: str = "SimpleAllocator"):
        super().__init__(name)

    async def allocate(self, signal_event: SignalEvent) -> AllocationWeights:
        """Allocate portfolio based on signal strength (simple implementation).
         
        Args:
            signal_event: Trading signal from strategy
             
        Returns:
            AllocationWeights containing portfolio weights
        """
        # In a real implementation, this would calculate optimal weights
        # based on risk, expected returns, correlation, etc.
        # For now, we just allocate based on signal strength
        
        # Normalize signal strength to allocation size (0 to 1)
        # Assuming signal strength is already normalized between 0 and 1
        allocation_size = signal_event.strength
        
        # Apply risk multiplier from meta-learner
        risk_multiplier = self.get_risk_multiplier()
        allocation_size = allocation_size * risk_multiplier
        
        # For simplicity, allocate to the signal's symbol only
        # In reality, we'd have a universe of symbols and optimize weights
        weights = {}
        if hasattr(signal_event, 'symbol') and signal_event.symbol:
            weights[signal_event.symbol] = allocation_size
        
        return AllocationWeights(
            timestamp=signal_event.timestamp,
            weights=weights,
            metadata={"allocator": self.name, "signal_strength": float(signal_event.strength), "risk_multiplier": float(risk_multiplier)}
        )