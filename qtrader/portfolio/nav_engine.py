from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Optional
from uuid import UUID, uuid4

from qtrader.core.events import NAVEvent, NAVPayload, EventType
from qtrader.core.state_store import SystemState, Position

logger = logging.getLogger(__name__)


class NAVEngine:
    """
    Real-time Net Asset Value (NAV) and Portfolio Accounting Engine.
    Provides institutional-grade Mark-to-Market (MtM) valuation and PnL separation.
    
    NAV = Cash + PortfolioMarketValue - CumulativeFees
    """

    def compute(self, state: SystemState, mark_prices: Dict[str, Decimal], trace_id: Optional[UUID] = None) -> NAVEvent:
        """
        Compute the latest NAV and PnL breakdown for the given system state.
        
        Args:
            state: The current SystemState (positions, cash, fees).
            mark_prices: Current market mark prices (e.g. Mid Price) per symbol.
            trace_id: Optional correlation ID for the resulting NAV event.
            
        Returns:
            NAVEvent: Containing the updated portfolio valuation.
        """
        total_market_value = Decimal('0')
        total_unrealized_pnl = Decimal('0')
        total_realized_pnl = Decimal('0')
        
        for symbol, pos in state.positions.items():
            # Get the mark price: Priority mark_prices > last known position market value
            price = mark_prices.get(symbol)
            
            if price is None:
                # Fallback to last known unit price from position if quantity is non-zero
                if pos.quantity != 0:
                    # Deriving last known price from market_value if available
                    if pos.market_value != 0:
                        price = pos.market_value / abs(pos.quantity)
                    else:
                        price = pos.average_price  # Extreme fallback
                    logger.warning(f"NAV_ENGINE | Missing live price for {symbol}, falling back to {price}")
                else:
                    price = Decimal('0')

            # 1. Calculate Mark-to-Market Value (V_i = q_i * P_i)
            mv = pos.quantity * price
            total_market_value += mv
            
            # 2. Unrealized PnL = Quantity * (CurrentPrice - EntryPrice)
            # This follows the provided mathematical model
            if pos.quantity != 0:
                upnl = pos.quantity * (price - pos.average_price)
                total_unrealized_pnl += upnl
                
            # 3. Aggregate Realized PnL (from closed positions/trades)
            total_realized_pnl += pos.realized_pnl

        # 4. Aggregate NAV
        # Standard Accounting: NAV = Cash + MarketValue - Fees
        # Realized PnL is usually reflected in Cash adjustments during trade settlement.
        nav = state.cash + total_market_value - state.total_fees
        
        logger.debug(f"NAV_ENGINE | NAV: {nav:.2f} | Cash: {state.cash:.2f} | MtM: {total_market_value:.2f}")

        return NAVEvent(
            trace_id=trace_id or uuid4(),
            source="NAVEngine",
            payload=NAVPayload(
                nav=float(nav),
                cash=float(state.cash),
                realized_pnl=float(total_realized_pnl),
                unrealized_pnl=float(total_unrealized_pnl),
                total_fees=float(state.total_fees)
            )
        )
