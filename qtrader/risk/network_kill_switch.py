"""Network-level kill switch for instant risk containment."""
import asyncio
import logging
from datetime import datetime

from qtrader.oms.oms_adapter import OMSAdapter

logger = logging.getLogger(__name__)

class NetworkKillSwitch:
    """
    Network-level kill switch for instant risk containment.
    
    When triggered, it:
    1. Cancels all open orders via the OMS adapter (in hard kill mode)
    2. Sets a flag to prevent new order submissions
    """

    def __init__(
        self,
        oms_adapter: OMSAdapter | None = None,
        logger_instance: logging.Logger | None = None,
        latency_threshold_ms: float = 500.0,
        max_errors: int = 5,
    ):
        """
        Initialize network kill switch.

        Args:
            oms_adapter: OMS adapter for order cancellation (optional)
            logger_instance: Logger instance (optional)
            latency_threshold_ms: Max allowed latency in ms before kill switch triggers.
            max_errors: Max allowed error count before kill switch triggers.
        """
        self.oms_adapter = oms_adapter
        self.logger = logger_instance or logger
        self.latency_threshold_ms = float(latency_threshold_ms)
        self.max_errors = int(max_errors)

        self._triggered = False
        self._trigger_reason: str | None = None
        self._triggered_at: datetime | None = None
        self._mode: str | None = None  # 'hard', 'soft', or None

        self._latency_history: list[float] = []
        self._error_count = 0

        self.logger.info("Network kill switch initialized")

    def record_latency(self, latency_ms: float) -> None:
        """Record a latency measurement and trigger if threshold exceeded."""
        val = float(latency_ms)
        self._latency_history.append(val)
        if val > self.latency_threshold_ms:
            reason = f"Latency threshold exceeded: {val}ms > {self.latency_threshold_ms}ms"
            self._triggered = True
            self._trigger_reason = reason
            self._triggered_at = datetime.now()
            self._mode = 'hard'
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.engage_hard_kill(reason))
            except RuntimeError:
                # No running loop (likely a sync unit test), just log it
                self.logger.critical(f"NETWORK KILL SWITCH ENGAGED (HARD KILL - SYNC): {reason}")

    def record_error(self) -> None:
        """Record a network error and trigger if threshold reached."""
        self._error_count += 1
        if self._error_count > self.max_errors:
            reason = f"Max errors exceeded: {self._error_count} > {self.max_errors}"
            self._triggered = True
            self._trigger_reason = reason
            self._triggered_at = datetime.now()
            self._mode = 'hard'
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.engage_hard_kill(reason))
            except RuntimeError:
                # No running loop (likely a sync unit test), just log it
                self.logger.critical(f"NETWORK KILL SWITCH ENGAGED (HARD KILL - SYNC): {reason}")

    def reset(self) -> None:
        """Reset the kill switch internally (metrics and trigger status)."""
        self._triggered = False
        self._trigger_reason = None
        self._triggered_at = None
        self._mode = None
        self._error_count = 0
        self._latency_history.clear()
        self.logger.info("Network kill switch metrics and status reset")

    @property
    def is_triggered(self) -> bool:
        """Check if kill switch is currently engaged (alias for is_engaged)."""
        return self._triggered

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

    def get_mode(self) -> str | None:
        """Get the current mode: 'hard', 'soft', or None."""
        return self._mode

    def get_reason(self) -> str | None:
        """Get the reason for triggering the kill switch."""
        return self._trigger_reason

    def get_triggered_at(self) -> datetime | None:
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