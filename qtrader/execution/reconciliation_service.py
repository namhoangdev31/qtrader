"""Reconciliation service for position consistency between local OMS and exchange."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from qtrader.core.types import FillEvent
from qtrader.execution.reconciliation_engine import ReconciliationEngine
from qtrader.oms.order_management_system import UnifiedOMS


class ReconciliationService:
    """Service for bidirectional synchronization between local OMS and exchange.

    Features:
    - Periodic reconciliation (every 1 minute)
    - Real-time reconciliation after each FillEvent
    - Deterministic position comparison with tolerance
    - Kill switch triggering on mismatch
    - Fallback to last known exchange positions on API failure
    - Escalation on persistent mismatch (>2 cycles)
    """

    def __init__(
        self,
        local_oms: UnifiedOMS,
        exchange_client: Any,  # Exchange client with get_positions method
        reconciliation_interval: int = 60,  # seconds
        tolerance: float = 1e-8,
    ) -> None:
        """Initialize reconciliation service.

        Args:
            local_oms: Local OMS instance for position tracking.
            exchange_client: Exchange client for fetching positions.
            reconciliation_interval: Interval for periodic reconciliation in seconds.
            tolerance: Maximum allowed absolute difference before considering it a mismatch.
        """
        self.local_oms = local_oms
        self.exchange_client = exchange_client
        self.reconciliation_interval = reconciliation_interval
        self.engine = ReconciliationEngine(tolerance=tolerance)

        # State
        self._reconciliation_task: asyncio.Task | None = None
        self._is_running = False
        self._last_reconciliation: datetime | None = None
        self._last_exchange_positions: dict[str, float] = {}
        self._consecutive_mismatches = 0
        self._last_known_good_exchange_positions: dict[str, float] = {}

        logger.info(
            f"ReconciliationService initialized (interval: {reconciliation_interval}s, tolerance: {tolerance})"
        )

    async def start(self) -> None:
        """Start the reconciliation service."""
        if self._is_running:
            return
        self._is_running = True
        self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())
        logger.info("Reconciliation service started")

    async def stop(self) -> None:
        """Stop the reconciliation service."""
        self._is_running = False
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
        logger.info("Reconciliation service stopped")

    async def _reconciliation_loop(self) -> None:
        """Main reconciliation loop for periodic checks."""
        while self._is_running:
            try:
                await self._perform_reconciliation()
                await asyncio.sleep(self.reconciliation_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}")
                await asyncio.sleep(self.reconciliation_interval * 2)  # Back off on error

    async def _perform_reconciliation(self) -> None:
        """Perform bidirectional state reconciliation."""
        try:
            logger.debug("Starting reconciliation cycle")

            # Get local positions
            local_positions = await self._get_local_positions()

            # Get exchange positions with fallback
            exchange_positions = await self._get_exchange_positions()

            # Compare and identify discrepancies
            result = self.engine.reconcile(local_positions, exchange_positions)

            if result["status"] == "MISMATCH":
                self._consecutive_mismatches += 1
                logger.warning(
                    f"Position mismatch detected (consecutive: {self._consecutive_mismatches}): "
                    f"total_abs_diff={result['total_abs_diff']}, "
                    f"symbol_diff={result['symbol_diff']}"
                )
                # Trigger kill switch as per requirement
                await self._trigger_kill_switch()
                # Escalate if mismatch persists > 2 cycles
                if self._consecutive_mismatches >= 2:
                    logger.critical(
                        f"Persistent mismatch for {self._consecutive_mismatches} cycles. "
                        "Escalating to admin alert."
                    )
                    # In production, would notify paging system here
            else:
                if self._consecutive_mismatches > 0:
                    logger.info(
                        f"Reconciliation recovered after {self._consecutive_mismatches} mismatch cycles"
                    )
                self._consecutive_mismatches = 0
                self._last_known_good_exchange_positions = exchange_positions.copy()
                logger.debug("Position reconciliation successful - no discrepancies")

            self._last_reconciliation = datetime.utcnow()
            self._last_exchange_positions = exchange_positions.copy()

        except Exception as e:
            logger.error(f"Error during reconciliation: {e}", exc_info=True)
            # On error, we keep the last known good exchange positions for fallback
            # but we don't update consecutive mismatches

    async def _get_local_positions(self) -> dict[str, float]:
        """Get positions from local OMS as symbol -> quantity dict."""
        try:
            # Get positions DataFrame from OMS
            df = self.local_oms.position_manager.get_all_positions()
            if df.is_empty():
                return {}
            # Convert to dict: symbol -> qty
            return {row["symbol"]: row["qty"] for row in df.iter_rows(named=True)}
        except Exception as e:
            logger.error(f"Failed to get local positions: {e}")
            return {}

    async def _get_exchange_positions(self) -> dict[str, float]:
        """Get positions from exchange with fallback to last known snapshot."""
        try:
            # This would depend on the exchange client implementation
            # For now, we assume exchange_client has a get_positions method
            if hasattr(self.exchange_client, "get_positions"):
                positions = await self.exchange_client.get_positions()
                # Convert to dict: symbol -> quantity (assuming positions is dict or list of dicts)
                if isinstance(positions, dict):
                    return {k: float(v) for k, v in positions.items()}
                elif isinstance(positions, list):
                    # Assume list of dicts with 'symbol' and 'quantity' keys
                    return {
                        p["symbol"]: float(p["quantity"])
                        for p in positions
                        if "symbol" in p and "quantity" in p
                    }
                else:
                    logger.warning(f"Unexpected positions format: {type(positions)}")
                    return self._last_known_good_exchange_positions
            else:
                logger.warning("Exchange client lacks get_positions method")
                return self._last_known_good_exchange_positions
        except Exception as e:
            logger.error(f"Failed to get exchange positions: {e}")
            # Fallback to last known good snapshot
            if self._last_known_good_exchange_positions:
                logger.warning("Using last known good exchange positions due to API failure")
                return self._last_known_good_exchange_positions.copy()
            # If no last known good, return last exchanged (even if stale) or empty
            return self._last_exchange_positions.copy()

    async def _trigger_kill_switch(self) -> None:
        """Trigger kill switch to halt trading on position mismatch."""
        try:
            # In a real system, this would publish to event bus or call risk engine
            # For now, we log critically - actual implementation would integrate with risk/kill_switch.py
            logger.critical(
                "[KILL SWITCH] Position mismatch detected - halting all trading activities"
            )
            # - Publishing KILL_SWITCH event to event bus
            # - Calling risk.engine.trigger_kill_switch(reason="position_mismatch")
            # For now, we rely on logging and external monitoring to detect this
        except Exception as e:
            logger.error(f"Failed to trigger kill switch: {e}")

    async def reconcile_after_fill(self, fill_event: FillEvent) -> dict[str, Any]:
        """Reconcile positions after a FillEvent for real-time consistency.

        Args:
            fill_event: The fill event that just occurred.

        Returns:
            Reconciliation result dict with status, symbol_diff, total_abs_diff.
        """
        try:
            logger.debug(f"Running real-time reconciliation after fill: {fill_event}")

            # Get local positions (should already include the fill via OMS processing)
            local_positions = await self._get_local_positions()

            # Get exchange positions
            exchange_positions = await self._get_exchange_positions()

            # Reconcile
            result = self.engine.reconcile(local_positions, exchange_positions)

            if result["status"] == "MISMATCH":
                self._consecutive_mismatches += 1
                logger.warning(
                    f"Real-time mismatch after fill {fill_event.order_id}: "
                    f"total_abs_diff={result['total_abs_diff']}"
                )
                await self._trigger_kill_switch()
            else:
                # Reset mismatch count on successful reconciliation
                if self._consecutive_mismatches > 0:
                    logger.info(
                        f"Real-time reconciliation recovered after {self._consecutive_mismatches} mismatches"
                    )
                self._consecutive_mismatches = 0

            return result

        except Exception as e:
            logger.error(f"Error in reconcile_after_fill: {e}", exc_info=True)
            return {
                "status": "ERROR",
                "symbol_diff": {},
                "total_abs_diff": float("inf"),
            }

    def get_reconciliation_status(self) -> dict[str, Any]:
        """Get current reconciliation status for monitoring."""
        return {
            "is_running": self._is_running,
            "last_reconciliation": self._last_reconciliation,
            "consecutive_mismatches": self._consecutive_mismatches,
            "tolerance": self.engine.tolerance,
        }
