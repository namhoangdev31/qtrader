import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from qtrader.core.events import SystemEvent
from qtrader.core.types import FillEvent, MarketData, SignalEvent
from qtrader.execution.trade_logger import TradeLogger

logger = logging.getLogger(__name__)

class ShadowFillEvent:
    def __init__(
        self,
        signal_id: str,
        symbol: str,
        timestamp: datetime,
        side: str,
        quantity: Decimal,
        fill_price: Decimal,
        slippage: float,
        latency: float,
    ) -> None:
        self.signal_id = signal_id
        self.symbol = symbol
        self.timestamp = timestamp
        self.side = side
        self.quantity = quantity
        self.fill_price = fill_price
        self.slippage = slippage
        self.latency = latency

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "side": self.side,
            "quantity": float(self.quantity),
            "fill_price": float(self.fill_price),
            "slippage": self.slippage,
            "latency": self.latency,
        }

class ShadowEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.shadow_mode = config.get("shadow_mode", False)
        self.data_lake_path = config.get("data_lake_path", "data_lake/shadow")
        self.orderbook_simulator = config.get("orderbook_simulator")
        self.slippage_model = config.get("slippage_model")
        self.latency_model = config.get("latency_model")
        self.event_bus = config.get("event_bus")
        self.recent_signals: dict[str, SignalEvent] = {}
        self.recent_shadow_fills: dict[str, ShadowFillEvent] = {}
        self.shadow_positions: dict[str, Decimal] = {}
        self.shadow_cost_basis: dict[str, Decimal] = {}
        self.metrics = {
            "shadow_pnl": 0.0,
            "shadow_realized_pnl": 0.0,
            "shadow_unrealized_pnl": 0.0,
            "slippage_diff": 0.0,
            "execution_error": 0.0,
        }
        self._running = False
        self._tasks = []
        self._shadow_start_time: datetime | None = None
        self.min_shadow_duration_s = config.get("min_shadow_duration_s", 7 * 24 * 3600)
        self._shadow_start_time = datetime.utcnow() if self.shadow_mode else None
        if self.shadow_mode:
            os.makedirs(self.data_lake_path, exist_ok=True)
        logger.info(
            f"ShadowEngine initialized | shadow_mode={self.shadow_mode} | min_duration={self.min_shadow_duration_s / 86400:.1f} days"
        )

    async def start(self) -> None:
        if not self.shadow_mode:
            logger.warning("Shadow engine started but shadow_mode is disabled")
            return
        if not self.event_bus:
            logger.error("Cannot start shadow engine: no event_bus available")
            return
        self._running = True
        self.event_bus.subscribe(SignalEvent, self._on_signal)
        self.event_bus.subscribe(MarketData, self._on_market_data)
        self.event_bus.subscribe(FillEvent, self._on_fill)
        logger.info("Shadow engine started and subscribed to events")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe(SignalEvent, self._on_signal)
            self.event_bus.unsubscribe(MarketData, self._on_market_data)
            self.event_bus.unsubscribe(FillEvent, self._on_fill)
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Shadow engine stopped")

    def _get_signal_id(self, signal: SignalEvent) -> str:
        if signal.metadata and isinstance(signal.metadata, dict):
            if "signal_id" in signal.metadata:
                return str(signal.metadata["signal_id"])
            if "id" in signal.metadata:
                return str(signal.metadata["id"])
        timestamp_str = signal.timestamp.strftime("%Y%m%d_%H%M%S_%f")
        return f"{signal.symbol}_{signal.signal_type}_{timestamp_str}"

    async def _on_signal(self, event: SignalEvent) -> None:
        if not self._running:
            return
        signal_id = self._get_signal_id(event)
        self.recent_signals[signal_id] = event
        logger.debug(f"Stored signal {signal_id} for shadow processing")

    async def _on_market_data(self, event: MarketData) -> None:
        if not self._running:
            return
        if self.orderbook_simulator:
            self.orderbook_simulator.update_orderbook(event.symbol, event)
            orderbook = self.orderbook_simulator.get_orderbook(event.symbol)
            if orderbook is None:
                logger.warning("No orderbook data for symbol %s after update", event.symbol)
                return
        else:
            logger.warning("Orderbook simulator not available, skipping shadow fill processing")
            return
        signals_to_process = list(self.recent_signals.items())
        for signal_id, signal in signals_to_process:
            await self._simulate_and_record(signal_id, signal, orderbook)
        unrealized = 0.0
        best_bid = orderbook["bids"][0][0] if orderbook["bids"] else Decimal("0")
        best_ask = orderbook["asks"][0][0] if orderbook["asks"] else Decimal("0")
        mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else Decimal("0")
        if mid_price > 0:
            for symbol, qty in self.shadow_positions.items():
                if qty == 0:
                    continue
                avg_cost = self.shadow_cost_basis.get(symbol, Decimal("0"))
                unrealized += float(qty) * (float(mid_price) - float(avg_cost))
        self.metrics["shadow_unrealized_pnl"] = unrealized
        self.metrics["shadow_pnl"] = self.metrics["shadow_realized_pnl"] + unrealized

    def _update_shadow_inventory(self, fill: ShadowFillEvent) -> None:
        symbol = fill.symbol
        qty = Decimal(str(fill.quantity)) if fill.side == "BUY" else -Decimal(str(fill.quantity))
        price = fill.fill_price
        current_qty = self.shadow_positions.get(symbol, Decimal("0"))
        if current_qty * qty < 0:
            avg_cost = self.shadow_cost_basis.get(symbol, Decimal("0"))
            close_qty = min(abs(current_qty), abs(qty))
            pnl_increment = float(close_qty) * (float(price) - float(avg_cost))
            if current_qty < 0:
                pnl_increment = -pnl_increment
            self.metrics["shadow_realized_pnl"] += pnl_increment
        elif current_qty * qty >= 0 or current_qty == 0:
            total_qty = abs(current_qty) + abs(qty)
            if total_qty > 0:
                old_cost = self.shadow_cost_basis.get(symbol, Decimal("0"))
                new_cost = (abs(current_qty) * old_cost + abs(qty) * price) / total_qty
                self.shadow_cost_basis[symbol] = new_cost
        self.shadow_positions[symbol] = current_qty + qty

    async def _on_fill(self, event: FillEvent) -> None:
        if not self._running:
            return
        matched_signal_id = None
        for signal_id, signal in self.recent_signals.items():
            if (
                signal.symbol == event.symbol
                and abs((signal.timestamp - event.timestamp).total_seconds()) < 5
            ):
                matched_signal_id = signal_id
                break
        if matched_signal_id and matched_signal_id in self.recent_shadow_fills:
            shadow_fill = self.recent_shadow_fills[matched_signal_id]
            await self._update_metrics(event, shadow_fill)
            logger.info(f"Updated metrics for signal {matched_signal_id}")

    async def _simulate_and_record(
        self, signal_id: str, signal: SignalEvent, orderbook: dict
    ) -> None:
        try:
            base_latency = self.latency_model.predict() if self.latency_model else 0.05
            volatility = Decimal(str(signal.metadata.get("volatility", 0.02)))
            vol_scaler = 1.0 + float(volatility) * 10.0
            latency = base_latency * vol_scaler
            fill_time = signal.timestamp + timedelta(seconds=latency)
            side = "buy" if signal.signal_type in ["LONG", "EXIT_SHORT"] else "sell"
            quantity = float(abs(signal.strength))
            if self.orderbook_simulator:
                order = {"size": quantity, "side": side, "type": "market"}
                sim_book = {
                    "bids": [(float(p), float(s)) for (p, s) in orderbook.get("bids", [])],
                    "asks": [(float(p), float(s)) for (p, s) in orderbook.get("asks", [])],
                }
                fill_result = self.orderbook_simulator.simulate_order(order, sim_book)
                fill_price = Decimal(str(fill_result["avg_price"]))
                slippage = Decimal(str(fill_result["slippage"]))
                if fill_price == 0:
                    best_bid = orderbook["bids"][0][0] if orderbook["bids"] else Decimal("0")
                    best_ask = orderbook["asks"][0][0] if orderbook["asks"] else Decimal("0")
                    mid_price = (best_bid + best_ask) / 2
                    fill_price = (
                        mid_price * Decimal("1.02")
                        if side == "buy"
                        else mid_price * Decimal("0.98")
                    )
                    slippage = fill_price - mid_price
            else:
                best_bid = orderbook["bids"][0][0] if orderbook["bids"] else Decimal("0")
                best_ask = orderbook["asks"][0][0] if orderbook["asks"] else Decimal("0")
                mid_price = (best_bid + best_ask) / 2
                fill_price = mid_price
                slippage = Decimal("0")
            shadow_fill = ShadowFillEvent(
                signal_id=signal_id,
                symbol=signal.symbol,
                timestamp=fill_time,
                side=side.upper(),
                quantity=Decimal(str(quantity)),
                fill_price=fill_price,
                slippage=float(slippage),
                latency=latency,
            )
            self.recent_shadow_fills[signal_id] = shadow_fill
            await self._write_shadow_fill(shadow_fill)
            self._update_shadow_inventory(shadow_fill)

            TradeLogger.log_trade(
                symbol=shadow_fill.symbol,
                side=shadow_fill.side,
                quantity=float(shadow_fill.quantity),
                price=float(shadow_fill.fill_price),
                trace_id=signal_id,
                timestamp=shadow_fill.timestamp,
            )
        except Exception as e:
            logger.error(f"Error simulating shadow fill for signal {signal_id}: {e}")

    async def _write_shadow_fill(self, shadow_fill: ShadowFillEvent) -> None:
        try:
            filename = f"shadow_fills_{datetime.now().strftime('%Y%m%d')}.jsonl"
            filepath = os.path.join(self.data_lake_path, filename)
            await asyncio.to_thread(self._append_shadow_fill, filepath, shadow_fill)
        except Exception as e:
            logger.error(f"Failed to write shadow fill to data lake: {e}")

    @staticmethod
    def _append_shadow_fill(filepath: str, shadow_fill: ShadowFillEvent) -> None:
        with open(filepath, "a") as f:
            f.write(json.dumps(shadow_fill.to_dict()) + "\n")

    async def _update_metrics(self, live_fill: FillEvent, shadow_fill: ShadowFillEvent) -> None:
        try:
            price_diff = float(live_fill.price) - float(shadow_fill.fill_price)
            self.metrics["slippage_diff"] += price_diff
            qty_diff = abs(float(live_fill.quantity) - float(shadow_fill.quantity))
            self.metrics["execution_error"] += qty_diff
            logger.debug(f"Updated metrics: slippage_diff={price_diff}, execution_error={qty_diff}")
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def compare_with_live(self, live_pnl: float, live_trade_count: int) -> dict[str, Any]:
        shadow_pnl = self.metrics["shadow_pnl"]
        shadow_trade_count = len(self.recent_shadow_fills)
        execution_gap = live_pnl - shadow_pnl
        tracking_error = abs(live_trade_count - shadow_trade_count)
        avg_slippage_gap = self.metrics["slippage_diff"] / max(1, live_trade_count)
        comparison = {
            "live_pnl": live_pnl,
            "shadow_pnl": shadow_pnl,
            "execution_gap": execution_gap,
            "execution_gap_pct": execution_gap / abs(shadow_pnl) * 100 if shadow_pnl != 0 else 0.0,
            "live_trade_count": live_trade_count,
            "shadow_trade_count": shadow_trade_count,
            "tracking_error": tracking_error,
            "avg_slippage_gap": avg_slippage_gap,
            "status": "HEALTHY" if abs(execution_gap) < abs(shadow_pnl) * 0.1 else "DEGRADED",
        }
        self.check_auto_disable(comparison)
        return comparison

    def check_auto_disable(self, comparison: dict[str, Any]) -> None:
        if not self.event_bus:
            return
        gap_pct = comparison.get("execution_gap_pct", 0.0)
        if gap_pct < -20.0:
            reason = f"SHADOW_AUTO_DISABLE | Execution Gap Breach: {gap_pct:.2f}%"
            logger.critical(reason)
            asyncio.create_task(
                self.event_bus.publish(
                    SystemEvent(type="SYSTEM", action="EMERGENCY_HALT", reason=reason)
                )
            )
        live_count = comparison.get("live_trade_count", 0)
        shadow_count = comparison.get("shadow_trade_count", 0)
        if shadow_count > 10:
            miss_rate = abs(live_count - shadow_count) / shadow_count
            if miss_rate > 0.3:
                reason = f"SHADOW_AUTO_DISABLE | High Tracking Error: {miss_rate:.2%} miss rate"
                logger.critical(reason)
                asyncio.create_task(
                    self.event_bus.publish(
                        SystemEvent(type="SYSTEM", action="EMERGENCY_HALT", reason=reason)
                    )
                )

    def get_metrics(self) -> dict[str, float]:
        return self.metrics.copy()

    def is_running(self) -> bool:
        return self._running

    def is_shadow_duration_met(self) -> bool:
        if self._shadow_start_time is None:
            return False
        elapsed = (datetime.utcnow() - self._shadow_start_time).total_seconds()
        return elapsed >= self.min_shadow_duration_s

    def get_shadow_duration_info(self) -> dict[str, Any]:
        if self._shadow_start_time is None:
            return {
                "started": False,
                "elapsed_s": 0,
                "elapsed_days": 0.0,
                "required_s": self.min_shadow_duration_s,
                "required_days": self.min_shadow_duration_s / 86400,
                "duration_met": False,
            }
        elapsed = (datetime.utcnow() - self._shadow_start_time).total_seconds()
        return {
            "started": True,
            "elapsed_s": elapsed,
            "elapsed_days": round(elapsed / 86400, 2),
            "required_s": self.min_shadow_duration_s,
            "required_days": round(self.min_shadow_duration_s / 86400, 2),
            "duration_met": elapsed >= self.min_shadow_duration_s,
            "remaining_days": max(0, round((self.min_shadow_duration_s - elapsed) / 86400, 2)),
        }

    def can_promote_to_live(self) -> tuple[bool, str]:
        if not self.is_shadow_duration_met():
            info = self.get_shadow_duration_info()
            return (
                False,
                f"Shadow duration not met: {info['elapsed_days']:.1f} / {info['required_days']:.1f} days ({info['remaining_days']:.1f} days remaining)",
            )
        return (True, "Shadow validation duration satisfied")

    def can_trade_live(self, symbol: str) -> tuple[bool, str]:
        if not self.shadow_mode:
            return (True, "Shadow mode disabled (Force Live)")
        (can_promote, reason) = self.can_promote_to_live()
        if not can_promote:
            return (False, reason)
        total_error = self.metrics.get("execution_error", 0.0)
        trade_count = len(self.recent_shadow_fills)
        if trade_count > 5:
            avg_error = total_error / trade_count
            if avg_error > 0.05:
                return (False, f"SHADOW_DEGRADATION | High Tracking Error: {avg_error:.2%}")
        return (True, "SHADOW_VALIDATED")