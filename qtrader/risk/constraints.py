from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from qtrader.core.events import OrderEvent
from qtrader.core.state_store import SystemState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskResult:
    """Standardized decision output from a risk constraint."""
    approved: bool
    reason: Optional[str] = None
    metric_value: Decimal = Decimal('0')
    threshold: Decimal = Decimal('0')


class RiskConstraint(ABC):
    """
    Abstract Base Class for all real-time risk constraints.
    
    Constraints must be stateless and deterministic, using only the 
    provided order and system state for evaluation.
    """

    @abstractmethod
    def validate(self, order: OrderEvent, state: SystemState) -> RiskResult:
        """
        Evaluate a new order against the current portfolio state.
        
        Returns:
            RiskResult: Categorical approval or rejection with metadata.
        """
        pass


class MaxExposureConstraint(RiskConstraint):
    """
    Enforces a hard limit on the Portfolio Gross Exposure.
    Formula: Σ |Position Value| ≤ MaxExposure
    """

    def __init__(self, max_exposure: Decimal) -> None:
        self.limit = max_exposure

    def validate(self, order: OrderEvent, state: SystemState) -> RiskResult:
        # 1. Calculate current gross exposure
        current_gross = Decimal('0')
        for pos in state.positions.values():
            current_gross += abs(pos.market_value)
            
        # 2. Calculate pro-forma impact of the new order
        # For simplicity in gating, we assume the trade increases exposure
        # (Conservative fail-safe approach)
        qty = Decimal(str(order.payload.quantity))
        price = Decimal(str(order.payload.price or 0.0))
        
        # If order price is missing (Market Order), we must use the current 
        # position's market price or last known price as a fallback.
        if price == 0 and order.payload.symbol in state.positions:
            price = state.positions[order.payload.symbol].average_price

        impact = abs(qty * price)
        total_pro_forma = current_gross + impact
        
        if total_pro_forma > self.limit:
            return RiskResult(
                approved=False,
                reason="MAX_EXPOSURE_VIOLATION",
                metric_value=total_pro_forma,
                threshold=self.limit
            )
            
        return RiskResult(approved=True)


class MaxLeverageConstraint(RiskConstraint):
    """
    Enforces a hard limit on the Portfolio Leverage.
    Formula: Gross Exposure / Net Asset Value (NAV) ≤ MaxLeverage
    """

    def __init__(self, max_leverage: Decimal) -> None:
        self.limit = max_leverage

    def validate(self, order: OrderEvent, state: SystemState) -> RiskResult:
        # 1. Calculate pro-forma gross exposure
        current_gross = Decimal('0')
        for pos in state.positions.values():
            current_gross += abs(pos.market_value)
            
        qty = Decimal(str(order.payload.quantity))
        price = Decimal(str(order.payload.price or 0.0))
        if price == 0 and order.payload.symbol in state.positions:
            price = state.positions[order.payload.symbol].average_price
            
        impact = abs(qty * price)
        total_gross = current_gross + impact
        
        # 2. Compare against NAV
        nav = state.portfolio_value
        if nav <= 0:
            return RiskResult(
                approved=False, 
                reason="INSOLVENT_PORTFOLIO_NAV", 
                metric_value=nav, 
                threshold=Decimal('0')
            )
            
        leverage = total_gross / nav
        if leverage > self.limit:
            return RiskResult(
                approved=False,
                reason="MAX_LEVERAGE_VIOLATION",
                metric_value=leverage,
                threshold=self.limit
            )
            
        return RiskResult(approved=True)


class VaRLimitConstraint(RiskConstraint):
    """
    Simple VaR-based hard gate.
    Formula: Portfolio VaR ≤ VaR_Limit
    """

    def __init__(self, var_limit: Decimal) -> None:
        self.limit = var_limit

    def validate(self, order: OrderEvent, state: SystemState) -> RiskResult:
        # Note: In a production system, this would involve a small covariance 
        # matrix multiplication. Here we check the current stored VaR state.
        current_var = state.risk_state.portfolio_var
        
        if current_var > self.limit:
            return RiskResult(
                approved=False,
                reason="VAR_LIMIT_VIOLATION",
                metric_value=current_var,
                threshold=self.limit
            )
            
        return RiskResult(approved=True)
