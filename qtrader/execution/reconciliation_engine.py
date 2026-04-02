import asyncio
import logging
from decimal import Decimal

from qtrader.core.event import EventType, FillEvent, TradingHaltEvent
from qtrader.core.state_store import StateStore
from qtrader.core.types import EventBusProtocol
from qtrader.oms.order_management_system import UnifiedOMS


class ReconciliationEngine:
    """Real-time position reconciliation engine.
    
    Subscribes to all Fill events and performs a mandatory audit between
    the internal OMS state and the actual Exchange exposure after every fill.
    
    Mathematical Model:
    Diff = Position_OMS - Position_Exchange
    Constraint: Diff == 0
    """

    def __init__(
        self, 
        event_bus: EventBusProtocol, 
        oms: UnifiedOMS, 
        state_store: StateStore
    ) -> None:
        self.event_bus = event_bus
        self.oms = oms
        self.state_store = state_store
        self._log = logging.getLogger("qtrader.execution.reconciliation")

    async def start(self) -> None:
        """Subscribe to necessary events for audit."""
        self.event_bus.subscribe(EventType.FILL, self._on_fill)
        self._log.info("RECONCILIATION_ENGINE | Monitoring started")

    async def _on_fill(self, event: FillEvent) -> None:
        """Mandatory audit triggered on every fill."""
        symbol = event.symbol
        
        # Give OMS 100ms to process the fill (internal event loop time)
        await asyncio.sleep(0.1) 
        
        oms_pos = await self.state_store.get_position(symbol)
        oms_qty = oms_pos.quantity if oms_pos else Decimal('0')
        
        # 2. Poll Exchange for actual position
        exchange_qty = await self._fetch_exchange_position(symbol)
        
        # 3. Reconcile
        diff = oms_qty - exchange_qty
        
        if abs(diff) > Decimal('1e-8'):
            self._log.critical(
                f"RECONCILIATION_HALT | Position mismatch for {symbol}! "
                f"OMS: {oms_qty} vs Exchange: {exchange_qty} | Diff: {diff}"
            )
            halt_event = TradingHaltEvent(
                reason="POSITION_MISMATCH",
                metadata={
                    "symbol": symbol,
                    "oms_qty": float(oms_qty),
                    "exchange_qty": float(exchange_qty),
                    "diff": float(diff)
                }
            )
            await self.event_bus.publish(EventType.TRADING_HALT, halt_event)

    async def _fetch_exchange_position(self, symbol: str) -> Decimal:
        """Fetch actual position from the broker adapter."""
        # For now, we take the first adapter that has the symbol
        for name, adapter in self.oms.adapters.items():
            try:
                balances = await adapter.get_balance()
                # Assuming crypto where asset name is position
                asset = symbol.split('/', maxsplit=1)[0].split('-', maxsplit=1)[0]
                return Decimal(str(balances.get(asset, 0)))
            except Exception as e:
                self._log.error(f"Failed to fetch exchange position from {name}: {e}")
        return Decimal('0')
