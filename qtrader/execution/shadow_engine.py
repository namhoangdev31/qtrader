"""Shadow trading engine for parallel execution without capital risk."""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from qtrader.core.types import (
    MarketData,
    SignalEvent,
    AllocationWeights,
    RiskMetrics,
    OrderEvent,
    FillEvent
)
from qtrader.execution.oms_adapter import OMSAdapter
from qtrader.execution.orderbook_enhanced import EnhancedOrderbookSimulator
from qtrader.execution.slippage_model import SlippageModel
from qtrader.execution.latency_model import LatencyModel

logger = logging.getLogger(__name__)

class ShadowEngine:
    """Executes trading logic in parallel with live system but without submitting real orders."""
    
    def __init__(self,
                 oms_adapter: OMSAdapter,
                 orderbook_simulator: EnhancedOrderbookSimulator,
                 slippage_model: SlippageModel,
                 latency_model: LatencyModel):
        self.oms_adapter = oms_adapter
        self.orderbook_simulator = orderbook_simulator
        self.slippage_model = slippage_model
        self.latency_model = latency_model
        self.shadow_positions: Dict[str, Decimal] = {}
        self.shadow_performance: Dict[str, Dict] = {}
        self.is_active = False
        
    async def start(self):
        """Start the shadow engine."""
        self.is_active = True
        logger.info("Shadow trading engine started")
        
    async def stop(self):
        """Stop the shadow engine."""
        self.is_active = False
        logger.info("Shadow trading engine stopped")
        
    async def process_signal(self, 
                           signal: SignalEvent,
                           market_data: MarketData) -> Optional[FillEvent]:
        """Process a trading signal through shadow execution pipeline."""
        if not self.is_active:
            return None
            
        try:
            symbol = signal.symbol
            
            # Get simulated orderbook for the symbol
            orderbook = await self.orderbook_simulator.get_orderbook(symbol)
            if not orderbook:
                logger.warning(f"No orderbook available for {symbol} in shadow mode")
                return None
                
            # Calculate slippage and latency
            slippage = await self.slippage_model.calculate_slippage(
                symbol=symbol,
                side=signal.signal_type,
                quantity=abs(signal.strength),  # Simplified - would use position sizing
                orderbook=orderbook,
                volatility=market_data.volatility if hasattr(market_data, 'volatility') else Decimal('0.02')
            )
            
            latency = await self.latency_model.get_total_latency()
            
            # Simulate order submission and fill
            # In a real implementation, this would be more sophisticated
            mid_price = (Decimal(str(orderbook['bids'][0][0])) + Decimal(str(orderbook['asks'][0][0]))) / Decimal('2')
            simulated_price = mid_price + slippage
            fill_quantity = signal.strength  # Would be determined by position sizing in reality
            
            # Create shadow fill event
            fill_event = FillEvent(
                order_id=f"shadow_{datetime.utcnow().timestamp()}",
                symbol=symbol,
                quantity=fill_quantity,
                price=simulated_price,
                timestamp=datetime.utcnow(),
                side=signal.signal_type,
                commission=abs(fill_quantity * simulated_price * Decimal('0.001'))  # 0.1% fee
            )
            
            # Update shadow positions
            current_pos = self.shadow_positions.get(symbol, Decimal('0'))
            self.shadow_positions[symbol] = current_pos + fill_quantity
            
            # Track performance
            if symbol not in self.shadow_performance:
                self.shadow_performance[symbol] = {
                    'total_pnl': Decimal('0'),
                    'total_fees': Decimal('0'),
                    'trade_count': 0,
                    'slippage_accum': Decimal('0'),
                    'latency_accum': Decimal('0')
                }
                
            perf = self.shadow_performance[symbol]
            perf['trade_count'] += 1
            perf['slippage_accum'] += abs(slippage)
            perf['latency_accum'] += latency
            
            logger.info(
                f"Shadow fill for {symbol}: {fill_quantity}@{simulated_price:.2f} "
                f"(slippage: {slippage:.4f}, latency: {latency:.2f}ms)"
            )
            
            return fill_event  # In shadow mode, we return the fill for tracking
            
        except Exception as e:
            logger.error(f"Error processing signal in shadow engine: {e}", exc_info=True)
            return None
            
    def get_shadow_positions(self) -> Dict[str, Decimal]:
        """Get current shadow positions."""
        return self.shadow_positions.copy()
        
    def get_shadow_performance(self) -> Dict[str, Dict]:
        """Get shadow performance metrics."""
        return {k: v.copy() for k, v in self.shadow_performance.items()}