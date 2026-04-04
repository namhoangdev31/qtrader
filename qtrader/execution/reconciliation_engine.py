import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal

from qtrader.core.events import EventType, FillEvent, SystemEvent, SystemPayload
from qtrader.core.state_store import StateStore
from qtrader.core.types import EventBusProtocol
from qtrader.oms.order_management_system import UnifiedOMS
from qtrader.risk.kill_switch import GlobalKillSwitch


class ReconciliationEngine:
    """Real-time position reconciliation engine.

    Subscribes to all Fill events and performs a mandatory audit between
    the internal OMS state and the actual Exchange exposure after every fill.

    Additionally runs periodic reconciliation every 60 seconds (Standash §4.9).

    Mathematical Model:
    Diff = Position_OMS - Position_Exchange
    Constraint: Diff == 0
    """

    def __init__(
        self,
        event_bus: EventBusProtocol,
        oms: UnifiedOMS,
        state_store: StateStore,
        recon_interval_s: float = 60.0,
        kill_switch: GlobalKillSwitch | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.oms = oms
        self.state_store = state_store
        self.recon_interval_s = recon_interval_s
        self.kill_switch = kill_switch
        self._log = logging.getLogger("qtrader.execution.reconciliation")
        self._fill_processed_events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self._periodic_task: asyncio.Task | None = None
        self._running = False
        self._last_recon_time: float = 0.0
        self._recon_count: int = 0
        self._mismatch_count: int = 0

    async def start(self) -> None:
        """Subscribe to necessary events and start periodic reconciliation."""
        self.event_bus.subscribe(EventType.FILL, self._on_fill)
        self._running = True
        self._periodic_task = asyncio.create_task(self._periodic_recon_loop())
        self._log.info(
            f"RECONCILIATION_ENGINE | Monitoring started | "
            f"Periodic interval: {self.recon_interval_s}s"
        )

    async def stop(self) -> None:
        """Stop periodic reconciliation."""
        self._running = False
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
        self._log.info("RECONCILIATION_ENGINE | Stopped")

    async def _periodic_recon_loop(self) -> None:
        """Standash §4.9: Periodic reconciliation every N seconds."""
        while self._running:
            try:
                await asyncio.sleep(self.recon_interval_s)
                await self._run_periodic_reconciliation()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Periodic reconciliation error: {e}", exc_info=True)

    async def _run_periodic_reconciliation(self) -> None:
        """Full portfolio reconciliation across all symbols."""
        self._log.info("PERIODIC_RECON | Starting full portfolio reconciliation")
        self._last_recon_time = time.time()
        self._recon_count += 1

        # Get all tracked positions from OMS
        oms_positions = await self._get_all_oms_positions()

        mismatches: list[dict] = []
        for symbol, oms_qty in oms_positions.items():
            try:
                exchange_qty = await self._fetch_exchange_position(symbol)
                diff = oms_qty - exchange_qty

                if abs(diff) > Decimal("1e-8"):
                    mismatches.append(
                        {
                            "symbol": symbol,
                            "oms_qty": float(oms_qty),
                            "exchange_qty": float(exchange_qty),
                            "diff": float(diff),
                        }
                    )
                    self._mismatch_count += 1
                    self._log.warning(
                        f"PERIODIC_RECON | Mismatch: {symbol} | "
                        f"OMS={oms_qty} vs EXCH={exchange_qty} | Diff={diff}"
                    )
            except Exception as e:
                self._log.error(f"PERIODIC_RECON | Failed to reconcile {symbol}: {e}")

        # If any mismatch, trigger halt
        if mismatches:
            self._log.critical(
                f"PERIODIC_RECON | {len(mismatches)} mismatch(es) detected | "
                f"Triggering TRADING_HALT"
            )
            # Trigger kill switch for reconciliation mismatch
            if self.kill_switch:
                self.kill_switch.trigger_on_critical_failure(
                    "RECON_MISMATCH",
                    f"{len(mismatches)} position mismatch(es) between OMS and exchange",
                )
            halt_event = SystemEvent(
                source="ReconciliationEngine",
                trace_id=getattr(self, "_trace_id", "periodic_recon"),
                payload=SystemPayload(
                    action="TRADING_HALT",
                    reason="PERIODIC_RECON_MISMATCH",
                    metadata={
                        "mismatch_count": len(mismatches),
                        "mismatches": mismatches,
                        "recon_count": self._recon_count,
                        "total_mismatches": self._mismatch_count,
                    },
                ),
            )
            await self.event_bus.publish(halt_event)
        else:
            self._log.info(
                f"PERIODIC_RECON | OK | {len(oms_positions)} symbols reconciled | "
                f"Recon #{self._recon_count}"
            )

    async def _get_all_oms_positions(self) -> dict[str, Decimal]:
        """Get all positions from the OMS."""
        positions: dict[str, Decimal] = {}
        # Iterate through all adapters and their symbols
        for name, adapter in self.oms.adapters.items():
            try:
                balances = await adapter.get_balance()
                for asset, qty in balances.items():
                    if qty != 0:
                        positions[asset] = positions.get(asset, Decimal("0")) + Decimal(str(qty))
            except Exception as e:
                self._log.error(f"Failed to get positions from {name}: {e}")
        return positions

    async def _on_fill(self, event: FillEvent) -> None:
        """Mandatory audit triggered on every fill."""
        symbol = event.payload.symbol
        order_id = event.payload.order_id

        # Event-driven wait: signal OMS to process, then wait for completion
        processed_event = self._fill_processed_events[order_id]
        processed_event.clear()

        # Wait for OMS processing with timeout instead of blind sleep
        try:
            await asyncio.wait_for(processed_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            self._log.warning(
                f"RECONCILIATION_ENGINE | OMS processing timeout for {symbol}/{order_id}"
            )

        oms_pos = await self.state_store.get_position(symbol)
        oms_qty = oms_pos.quantity if oms_pos else Decimal("0")

        # 2. Poll Exchange for actual position
        exchange_qty = await self._fetch_exchange_position(symbol)

        # 3. Reconcile
        diff = oms_qty - exchange_qty

        if abs(diff) > Decimal("1e-8"):
            self._log.critical(
                f"RECONCILIATION_HALT | Position mismatch for {symbol}! "
                f"OMS: {oms_qty} vs Exchange: {exchange_qty} | Diff: {diff}"
            )
            halt_event = SystemEvent(
                source="ReconciliationEngine",
                trace_id=getattr(event, "trace_id", "unknown"),
                payload=SystemPayload(
                    action="TRADING_HALT",
                    reason="POSITION_MISMATCH",
                    metadata={
                        "symbol": symbol,
                        "oms_qty": float(oms_qty),
                        "exchange_qty": float(exchange_qty),
                        "diff": float(diff),
                    },
                ),
            )
            await self.event_bus.publish(halt_event)

    async def _fetch_exchange_position(self, symbol: str) -> Decimal:
        """Fetch actual position from the broker adapter."""
        # For now, we take the first adapter that has the symbol
        for name, adapter in self.oms.adapters.items():
            try:
                balances = await adapter.get_balance()
                # Assuming crypto where asset name is position
                asset = symbol.split("/", maxsplit=1)[0].split("-", maxsplit=1)[0]
                return Decimal(str(balances.get(asset, 0)))
            except Exception as e:
                self._log.error(f"Failed to fetch exchange position from {name}: {e}")
        return Decimal("0")

    def signal_oms_processed(self, order_id: str) -> None:
        """Signal that OMS has finished processing a fill (called by OMS after fill handling)."""
        if order_id in self._fill_processed_events:
            self._fill_processed_events[order_id].set()

    def get_status(self) -> dict:
        """Return reconciliation status for monitoring."""
        return {
            "running": self._running,
            "recon_interval_s": self.recon_interval_s,
            "last_recon_time": self._last_recon_time,
            "recon_count": self._recon_count,
            "mismatch_count": self._mismatch_count,
        }
