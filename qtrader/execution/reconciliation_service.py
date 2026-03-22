"""Bidirectional OMS state reconciliation service with exchange."""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from qtrader.core.types import Position, OrderEvent, FillEvent
from qtrader.execution.oms_adapter import OMSAdapter
from qtrader.execution.oms import OMS

logger = logging.getLogger(__name__)

class ReconciliationService:
    """Service for bidirectional synchronization between local OMS and exchange."""
    
    def __init__(self,
                 local_oms: OMS,
                 exchange_client: object,  # Generic exchange client interface
                 reconciliation_interval: int = 30):  # seconds
        self.local_oms = local_oms
        self.exchange_client = exchange_client
        self.reconciliation_interval = reconciliation_interval
        self._reconciliation_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._last_reconciliation: Optional[datetime] = None
        self._logger = logger
        
    async def start(self):
        """Start the reconciliation service."""
        if self._is_running:
            return
        self._is_running = True
        self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())
        self._logger.info(f"Reconciliation service started (interval: {self.reconciliation_interval}s)")
        
    async def stop(self):
        """Stop the reconciliation service."""
        self._is_running = False
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
        self._logger.info("Reconciliation service stopped")
        
    async def _reconciliation_loop(self):
        """Main reconciliation loop."""
        while self._is_running:
            try:
                await self._perform_reconciliation()
                await asyncio.sleep(self.reconciliation_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in reconciliation loop: {e}")
                await asyncio.sleep(self.reconciliation_interval * 2)  # Back off on error
                
    async def _perform_reconciliation(self):
        """Perform bidirectional state reconciliation."""
        try:
            self._logger.debug("Starting OMS reconciliation cycle")
            
            # Get local positions
            local_positions = await self._get_local_positions()
            
            # Get exchange positions
            exchange_positions = await self._get_exchange_positions()
            
            # Compare and identify discrepancies
            discrepancies = self._compare_positions(local_positions, exchange_positions)
            
            if discrepancies:
                self._logger.warning(f"Position discrepancies found: {discrepancies}")
                # In a real system, we might adjust local OMS or alert for manual intervention
                # For safety, we prefer to alert rather than auto-correct in live trading
                await self._handle_discrepancies(discrepancies)
            else:
                self._logger.debug("Position reconciliation successful - no discrepancies")
                
            # Reconcile open orders
            await self._reconcile_orders()
            
            self._last_reconciliation = datetime.utcnow()
            
        except Exception as e:
            self._logger.error(f"Error during reconciliation: {e}", exc_info=True)
            
    async def _get_local_positions(self) -> Dict[str, Position]:
        """Get positions from local OMS."""
        # This would depend on the OMS implementation
        # For now, we'll return an empty dict as a placeholder
        # In a real implementation, this would query the OMS for current positions
        return {}
        
    async def _get_exchange_positions(self) -> Dict[str, Position]:
        """Get positions from exchange."""
        # This would depend on the exchange client implementation
        # For now, we'll return an empty dict as a placeholder
        return {}
        
    def _compare_positions(self, 
                         local: Dict[str, Position],
                         exchange: Dict[str, Position]) -> Dict[str, Dict]:
        """Compare local and exchange positions and return discrepancies."""
        discrepancies = {}
        all_symbols = set(local.keys()) | set(exchange.keys())
        
        for symbol in all_symbols:
            local_pos = local.get(symbol, Position(symbol=symbol, quantity=0))
            exchange_pos = exchange.get(symbol, Position(symbol=symbol, quantity=0))
            
            if local_pos.quantity != exchange_pos.quantity:
                discrepancies[symbol] = {
                    'local': local_pos.quantity,
                    'exchange': exchange_pos.quantity,
                    'difference': exchange_pos.quantity - local_pos.quantity
                }
                
        return discrepancies
        
    async def _reconcile_orders(self):
        """Reconcile open orders between local OMS and exchange."""
        try:
            # Get local open orders
            local_orders = await self._get_local_open_orders()
            
            # Get exchange open orders
            exchange_orders = await self._get_exchange_open_orders()
            
            # Log any significant discrepancies for investigation
            if len(local_orders) != len(exchange_orders):
                self._logger.info(
                    f"Order count mismatch - Local: {len(local_orders)}, Exchange: {len(exchange_orders)}"
                )
                
        except Exception as e:
            self._logger.error(f"Error reconciling orders: {e}")
            
    async def _get_local_open_orders(self) -> List[OrderEvent]:
        """Get open orders from local OMS."""
        # Placeholder implementation
        return []
        
    async def _get_exchange_open_orders(self) -> List[OrderEvent]:
        """Get open orders from exchange."""
        # Placeholder implementation
        return []
        
    async def _handle_discrepancies(self, discrepancies: Dict[str, Dict]):
        """Handle position discrepancies (alerting, potential correction)."""
        # In production, this would trigger alerts to operators
        # For automated systems, we might have configurable auto-correction thresholds
        for symbol, disc in discrepancies.items():
            self._logger.critical(
                f"POSITION DISCREPANCY - {symbol}: "
                f"Local={disc['local']}, Exchange={disc['exchange']}, "
                f"Diff={disc['difference']}"
            )
            # Example: send alert via notification system
            # await self.notification_service.send_alert(
            #     f"Position discrepancy detected for {symbol}: {disc}"
            # )