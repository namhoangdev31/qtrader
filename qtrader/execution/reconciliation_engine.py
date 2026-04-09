import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from qtrader.core.events import EventType, FillEvent, SystemEvent, SystemPayload
from qtrader.core.state_store import Position
from qtrader.core.types import EventBusProtocol
from qtrader.oms.order_management_system import UnifiedOMS
from qtrader.risk.kill_switch import GlobalKillSwitch


class ReconciliationEngine:
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
        self._last_audit: dict[str, Any] = {}

    async def start(self) -> None:
        self.event_bus.subscribe(EventType.FILL, self._on_fill)
        self.event_bus.subscribe(EventType.SYSTEM, self._on_system_event)
        self._running = True
        self._log.info(
            f"RECONCILIATION_ENGINE | Monitoring started | Periodic interval: {self.recon_interval_s}s"
        )

    async def stop(self) -> None:
        self._running = False
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
        self._log.info("RECONCILIATION_ENGINE | Stopped")

    async def _on_system_event(self, event: Any) -> None:
        if not self._running:
            return

        if isinstance(event, SystemEvent) and event.payload.action == "HEARTBEAT":
            now = time.time()
            if now - self._last_recon_time >= self.recon_interval_s:
                asyncio.create_task(self._run_periodic_reconciliation())

    async def _run_periodic_reconciliation(self) -> None:
        self._log.info("PERIODIC_RECON | Starting full portfolio reconciliation")
        self._last_recon_time = time.time()
        self._recon_count += 1
        oms_positions = await self._get_all_oms_positions()
        all_symbols = set(oms_positions.keys())
        for _name, adapter in self.oms.adapters.items():
            try:
                balances = await adapter.get_balance()
                for asset in balances:
                    all_symbols.add(asset)
            except Exception:
                pass
        mismatches: list[dict] = []
        for symbol in all_symbols:
            oms_qty = oms_positions.get(symbol, Decimal("0"))
            try:
                exchange_qty = await self._fetch_exchange_position(symbol)
                diff = oms_qty - exchange_qty
                if abs(diff) > Decimal("1e-5"):
                    if oms_qty == 0 and exchange_qty != 0:
                        self._log.info(
                            f"PERIODIC_RECON | First-run sync: {symbol} -> {exchange_qty}"
                        )

                        pos = Position(
                            symbol=symbol,
                            quantity=exchange_qty,
                            average_price=Decimal("0"),
                            timestamp=datetime.now(),
                        )
                        await self.state_store.set_position(pos)
                        continue
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
                        f"PERIODIC_RECON | Mismatch: {symbol} | OMS={oms_qty} vs EXCH={exchange_qty} | Diff={diff}"
                    )
            except Exception as e:
                self._log.error(f"PERIODIC_RECON | Failed to reconcile {symbol}: {e}")
        if mismatches:
            self._log.critical(
                f"PERIODIC_RECON | {len(mismatches)} mismatch(es) detected | Triggering TRADING_HALT"
            )
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
            self._log.info(f"Recon #{self._recon_count}")
        self._last_audit = {
            "timestamp": self._last_recon_time,
            "mismatches": mismatches,
            "mismatch_count": len(mismatches),
            "total_symbols": len(oms_positions),
            "status": "ERROR" if mismatches else "OK",
        }

    def get_last_audit(self) -> dict[str, Any]:
        return self._last_audit

    async def _get_all_oms_positions(self) -> dict[str, Decimal]:
        positions: dict[str, Decimal] = {}
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
        symbol = event.payload.symbol
        order_id = event.payload.order_id
        processed_event = self._fill_processed_events[order_id]
        processed_event.clear()
        try:
            await asyncio.wait_for(processed_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            self._log.warning(
                f"RECONCILIATION_ENGINE | OMS processing timeout for {symbol}/{order_id}"
            )
        oms_pos = await self.state_store.get_position(symbol)
        oms_qty = oms_pos.quantity if oms_pos else Decimal("0")
        exchange_qty = await self._fetch_exchange_position(symbol)
        diff = oms_qty - exchange_qty
        if abs(diff) > Decimal("1e-8"):
            self._log.critical(
                f"RECONCILIATION_HALT | Position mismatch for {symbol}! OMS: {oms_qty} vs Exchange: {exchange_qty} | Diff: {diff}"
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
        for name, adapter in self.oms.adapters.items():
            try:
                balances = await adapter.get_balance()
                asset = symbol.split("/", maxsplit=1)[0].split("-", maxsplit=1)[0]
                return Decimal(str(balances.get(asset, 0)))
            except Exception as e:
                self._log.error(f"Failed to fetch exchange position from {name}: {e}")
        return Decimal("0")

    def signal_oms_processed(self, order_id: str) -> None:
        if order_id in self._fill_processed_events:
            self._fill_processed_events[order_id].set()

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "recon_interval_s": self.recon_interval_s,
            "last_recon_time": self._last_recon_time,
            "recon_count": self._recon_count,
            "mismatch_count": self._mismatch_count,
        }
