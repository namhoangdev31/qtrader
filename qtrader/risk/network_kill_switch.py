"""Network-level kill switch for instant risk containment."""
import asyncio
import logging
from typing import Optional
from datetime import datetime

from qtrader.execution.oms_adapter import OMSAdapter

logger = logging.getLogger(__name__)

class NetworkKillSwitch:
    """
    Network-level kill switch for instant risk containment.
    
    When triggered, it:
    1. Cancels all open orders via the OMS adapter (in hard kill mode)
    2. Sets a flag to prevent new order submissions
    """

    def __init__(self, oms_adapter: Optional[OMSAdapter] = None, logger_instance: Optional[logging.Logger] = None):
        """
        Initialize network kill switch.

        Args:
            oms_adapter: OMS adapter for order cancellation (optional)
            logger_instance: Logger instance (optional)
        """
        self.oms_adapter = oms_adapter
        self.logger = logger_instance or logger
        self._triggered = False
        self._trigger_reason: Optional[str] = None
        self._triggered_at: Optional[datetime] = None
        self._mode: Optional[str] = None  # 'hard', 'soft', or None

        self.logger.info("Network kill switch initialized")

    async def engage_hard_kill(self, reason: str = "Risk limit breach") -> None:
        """
        Engage hard kill mode: cancel all open orders and block new orders.

        Args:
            reason: Reason for triggering the kill switch
        """
        if self._triggered:
            self.logger.warning(
                f"Kill switch already triggered. Ignoring request: {reason}"
            )
            return

        self._triggered = True
        self._trigger_reason = reason
        self._triggered_at = datetime.now()
        self._mode = 'hard'

        self.logger.critical(
            f"NETWORK KILL SWITCH ENGAGED (HARD KILL): {reason} at {self._triggered_at.isoformat()}"
        )

        # Cancel all open orders via OMS adapter
        if self.oms_adapter:
            try:
                # Check if the OMS adapter has a cancel_all_orders method
                if hasattr(self.oms_adapter, 'cancel_all_orders'):
                    # Note: This might be an async method in a real implementation.
                    # For now, we call it and assume it's synchronous or we don't need to await.
                    # In a production system, we would need to handle this appropriately.
                    if asyncio.iscoroutinefunction(self.oms_adapter.cancel_all_orders):
                        await self.oms_adapter.cancel_all_orders()
                    else:
                        # Call synchronous method; result intentionally ignored
                        result = self.oms_adapter.cancel_all_orders()
                    self.logger.info("Cancelled all open orders via OMS adapter")
                else:
                    self.logger.warning(
                        "OMS adapter does not have cancel_all_orders method. "
                        "Order cancellation must be handled separately."
                    )
            except Exception as e:
                self.logger.error(f"Error cancelling open orders: {e}")
        else:
            self.logger.warning("No OMS adapter provided, cannot cancel orders")

    async def engage_soft_stop(self, reason: str = "Soft stop triggered") -> None:
        """
        Engage soft stop mode: block new order submissions but do not cancel existing orders.

        Args:
            reason: Reason for triggering the soft stop
        """
        if self._triggered:
            self.logger.warning(
                f"Kill switch already triggered. Ignoring request: {reason}"
            )
            return

        self._triggered = True
        self._trigger_reason = reason
        self._triggered_at = datetime.now()
        self._mode = 'soft'

        self.logger.warning(
            f"NETWORK KILL SWITCH ENGAGED (SOFT STOP): {reason} at {self._triggered_at.isoformat()}"
        )

        # In soft stop, we do not cancel existing orders, only prevent new ones

    async def disengage(self) -> None:
        """Disengage the kill switch and return to normal operation."""
        if not self._triggered:
            self.logger.warning("Kill switch is not triggered, cannot disengage")
            return

        self.logger.info(
            f"Disengaging network kill switch at {self._triggered_at.isoformat() if self._triggered_at else 'unknown'} "
            f"with reason: {self._trigger_reason}"
        )
        
        self._triggered = False
        self._trigger_reason = None
        self._triggered_at = None
        self._mode = None

        self.logger.info("Network kill switch disengaged - normal operation restored")

    def is_engaged(self) -> bool:
        """Check if kill switch is currently engaged."""
        return self._triggered

    def get_mode(self) -> Optional[str]:
        """Get the current mode: 'hard', 'soft', or None."""
        return self._mode

    def get_reason(self) -> Optional[str]:
        """Get the reason for triggering the kill switch."""
        return self._trigger_reason

    def get_triggered_at(self) -> Optional[datetime]:
        """Get the timestamp when the kill switch was triggered."""
        return self._triggered_at

    def get_status(self) -> dict:
        """Get the status of the kill switch."""
        return {
            "triggered": self._triggered,
            "mode": self._mode,
            "triggered_at": self._triggered_at,
            "trigger_reason": self._trigger_reason
        }