"""Network-level hard kill switch for instant risk containment."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from qtrader.execution.oms_adapter import OMSAdapter

logger = logging.getLogger(__name__)

class NetworkKillSwitch:
    """
    Network-level kill switch for instant risk containment.
    
    When triggered, it:
    1. Sets a flag to prevent new order submissions (immediate, <10ms)
    2. Asynchronously cancels all open orders (if OMS adapter provides cancel_all_orders)
    """

    def __init__(self, oms_adapter: Optional[OMSAdapter] = None):
        """
        Initialize network kill switch.

        Args:
            oms_adapter: OMS adapter for order cancellation (optional)
        """
        self.oms_adapter = oms_adapter
        self._triggered = False
        self._trigger_reason: Optional[str] = None
        self._triggered_at: Optional[datetime] = None

        logger.info("Network kill switch initialized")

    def engage_hard_kill(self, reason: str = "Risk limit breach") -> None:
        """
        Engage hard kill mode: cancel all open orders and block new orders.

        Args:
            reason: Reason for triggering the kill switch
        """
        if self._triggered:
            logger.warning(
                f"Kill switch already triggered. Ignoring request: {reason}"
            )
            return

        self._triggered = True
        self._trigger_reason = reason
        self._triggered_at = datetime.now()

        logger.critical(
            f"NETWORK KILL SWITCH ENGAGED (HARD KILL): {reason}",
            trigger_time_val=self._triggered_at.isoformat()
        )

        # Cancel all open orders via OMS adapter as a background task
        if self.oms_adapter:
            try:
                if hasattr(self.oms_adapter, 'cancel_all_orders'):
                    # Launch as background task to avoid delaying the engagement
                    if asyncio.iscoroutinefunction(self.oms_adapter.cancel_all_orders):
                        asyncio.create_task(self.oms_adapter.cancel_all_orders())
                    else:
                        asyncio.create_task(
                            asyncio.to_thread(self.oms_adapter.cancel_all_orders)
                        )
                    logger.info("Cancelled all open orders via OMS adapter (launched as background task)")
                else:
                    logger.warning(
                        "OMS adapter does not have cancel_all_orders method. "
                        "Order cancellation must be handled separately."
                    )
            except Exception as e:
                logger.error(f"Error launching order cancellation: {e}")
        else:
            logger.warning("No OMS adapter provided, cannot cancel orders")

    def engage_soft_stop(self, reason: str = "Risk limit breach") -> None:
        """
        Engage soft stop mode: block new order submissions only.

        Args:
            reason: Reason for triggering the kill switch
        """
        if self._triggered:
            logger.warning(
                f"Kill switch already triggered. Ignoring request: {reason}"
            )
            return

        self._triggered = True
        self._trigger_reason = reason
        self._triggered_at = datetime.now()

        logger.warning(
            f"NETWORK KILL SWITCH ENGAGED (SOFT STOP): {reason}",
            trigger_time_val=self._triggered_at.isoformat()
        )
        # Note: In soft stop, we only set the flag. No order cancellation.

    def disengage(self) -> None:
        """Disengage the kill switch and return to normal operation."""
        if not self._triggered:
            logger.warning("Kill switch is not triggered, cannot disengage")
            return

        logger.info(
            f"Disengaging network kill switch",
            trigger_time_val=self._triggered_at.isoformat() if self._triggered_at else None,
            reason=self._trigger_reason
        )
        
        self._triggered = False
        self._trigger_reason = None
        self._triggered_at = None

        logger.info("Network kill switch disengaged - normal operation restored")

    def is_engaged(self) -> bool:
        """Check if kill switch is currently engaged."""
        return self._triggered

    def get_reason(self) -> Optional[str]:
        """Get the reason for triggering the kill switch."""
        return self._trigger_reason

    def get_triggered_at(self) -> Optional[datetime]:
        """Get the timestamp when the kill switch was triggered."""
        return self._triggered_at

    def allow_new_order_submission(self) -> bool:
        """Check if new order submissions are allowed."""
        return not self._triggered