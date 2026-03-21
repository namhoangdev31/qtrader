"""OMS adapter for order creation and submission."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from qtrader.core.types import AllocationWeights, RiskMetrics, OrderEvent
from qtrader.core.logger import logger


class OMSAdapter(ABC):
    """Abstract base class for OMS adapters."""

    def __init__(self, name: str = "OMSAdapter"):
        self.name = name
        self.logger = logger

    @abstractmethod
    async def create_order(
        self, 
        allocation_weights: AllocationWeights, 
        risk_metrics: RiskMetrics
    ) -> OrderEvent:
        """Create an order based on allocation weights and risk metrics.
        
        Args:
            allocation_weights: Portfolio allocation weights
            risk_metrics: Current risk metrics
            
        Returns:
            OrderEvent to be submitted to the OMS
        """
        pass


# Simple implementation that creates market orders based on allocation
class SimpleOMSAdapter(OMSAdapter):
    """Simple OMS adapter that creates market orders."""

    def __init__(self, name: str = "SimpleOMSAdapter"):
        super().__init__(name)

    async def create_order(
        self, 
        allocation_weights: AllocationWeights, 
        risk_metrics: RiskMetrics
    ) -> OrderEvent:
        """Create market orders based on allocation weights (simple implementation).
        
        Args:
            allocation_weights: Portfolio allocation weights
            risk_metrics: Current risk metrics
            
        Returns:
            OrderEvent to be submitted to the OMS
        """
        # In a real implementation, this would:
        # 1. Check risk limits
        # 2. Convert weights to target positions
        # 3. Calculate order sizes based on current positions
        # 4. Apply execution algorithms (TWAP, VWAP, etc.)
        # 5. Handle fractional shares, minimum order sizes, etc.
        
        # For now, we just create a simple market order for the first symbol
        # with weight > 0
        symbol = None
        weight = Decimal('0')
        
        for sym, w in allocation_weights.weights.items():
            if w > weight:
                symbol = sym
                weight = w
        
        if symbol is None or weight <= Decimal('0'):
            # No allocation to trade
            return OrderEvent(
                order_id="NO_TRADE",
                symbol="",
                timestamp=allocation_weights.timestamp,
                order_type="MARKET",
                side="BUY",  # Default, but quantity will be 0
                quantity=Decimal('0'),
                metadata={"reason": "no_allocation"}
            )
        
        # Simple order sizing: use weight as percentage of portfolio
        # In reality, this would be based on portfolio value and risk limits
        order_size = weight  # Simplified
        
        # Determine side based on signal (this would come from strategy in reality)
        # For now, assume long positions only
        side = "BUY"
        
        return OrderEvent(
            order_id=f"ORDER_{symbol}_{allocation_weights.timestamp.timestamp()}",
            symbol=symbol,
            timestamp=allocation_weights.timestamp,
            order_type="MARKET",
            side=side,
            quantity=order_size,
            metadata={
                "allocated_weight": float(weight),
                "risk_metrics": {
                    "portfolio_var": float(risk_metrics.portfolio_var),
                    "portfolio_volatility": float(risk_metrics.portfolio_volatility),
                }
            }
        )