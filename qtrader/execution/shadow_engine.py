import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json
from decimal import Decimal

from qtrader.core.types import SignalEvent, MarketData, FillEvent
from qtrader.execution.orderbook_enhanced import OrderbookEnhanced as OrderbookSimulator
from qtrader.execution.slippage_model import SlippageModel
from qtrader.execution.latency_model import LatencyModel

logger = logging.getLogger(__name__)

class ShadowFillEvent:
    """Represents a simulated fill in shadow mode."""
    def __init__(self, signal_id: str, symbol: str, timestamp: datetime,
                 side: str, quantity: Decimal, fill_price: Decimal,
                 slippage: float, latency: float):
        self.signal_id = signal_id
        self.symbol = symbol
        self.timestamp = timestamp
        self.side = side
        self.quantity = quantity
        self.fill_price = fill_price
        self.slippage = slippage
        self.latency = latency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "side": self.side,
            "quantity": float(self.quantity),
            "fill_price": float(self.fill_price),
            "slippage": self.slippage,
            "latency": self.latency
        }

class ShadowEngine:
    """
    Shadow engine that runs parallel to live trading system.
    Simulates order execution without sending real orders.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize shadow engine.

        Args:
            config: Configuration dictionary with keys:
                - shadow_mode: bool (enable/disable shadow mode)
                - data_lake_path: str (path to store shadow fills)
                - orderbook_simulator: OrderbookSimulator instance
                - slippage_model: SlippageModel instance
                - latency_model: LatencyModel instance
                - event_bus: EventBus instance (optional)
        """
        self.config = config
        self.shadow_mode = config.get("shadow_mode", False)
        self.data_lake_path = config.get("data_lake_path", "data_lake/shadow")
        self.orderbook_simulator = config.get("orderbook_simulator")
        self.slippage_model = config.get("slippage_model")
        self.latency_model = config.get("latency_model")
        self.event_bus = config.get("event_bus")

        # Internal state
        self.recent_signals: Dict[str, SignalEvent] = {}
        self.recent_shadow_fills: Dict[str, ShadowFillEvent] = {}
        self.metrics = {
            "shadow_pnl": 0.0,
            "slippage_diff": 0.0,
            "execution_error": 0.0
        }
        self._running = False
        self._tasks = []

        # Ensure data lake directory exists
        if self.shadow_mode:
            os.makedirs(self.data_lake_path, exist_ok=True)

        logger.info(f"ShadowEngine initialized with shadow_mode={self.shadow_mode}")

    async def start(self):
        """Start the shadow engine by subscribing to events."""
        if not self.shadow_mode:
            logger.warning("Shadow engine started but shadow_mode is disabled")
            return

        if not self.event_bus:
            logger.error("Cannot start shadow engine: no event_bus available")
            return

        self._running = True
        # Subscribe to events
        self.event_bus.subscribe(SignalEvent, self._on_signal)
        self.event_bus.subscribe(MarketData, self._on_market_data)
        self.event_bus.subscribe(FillEvent, self._on_fill)

        logger.info("Shadow engine started and subscribed to events")

    async def stop(self):
        """Stop the shadow engine and clean up."""
        if not self._running:
            return

        self._running = False
        if self.event_bus:
            self.event_bus.unsubscribe(SignalEvent, self._on_signal)
            self.event_bus.unsubscribe(MarketData, self._on_market_data)
            self.event_bus.unsubscribe(FillEvent, self._on_fill)

        # Cancel any running tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("Shadow engine stopped")

    def _get_signal_id(self, signal: SignalEvent) -> str:
        """Extract or generate a unique signal ID."""
        # Try to get ID from metadata
        if signal.metadata and isinstance(signal.metadata, dict):
            if 'signal_id' in signal.metadata:
                return str(signal.metadata['signal_id'])
            if 'id' in signal.metadata:
                return str(signal.metadata['id'])

        # Generate ID from symbol, timestamp, and signal_type
        # This is not ideal but better than nothing
        timestamp_str = signal.timestamp.strftime("%Y%m%d_%H%M%S_%f")
        return f"{signal.symbol}_{signal.signal_type}_{timestamp_str}"

    async def _on_signal(self, event: SignalEvent):
        """Handle incoming signal event."""
        if not self._running:
            return

        # Store signal for matching with fills
        signal_id = self._get_signal_id(event)
        self.recent_signals[signal_id] = event
        logger.debug(f"Stored signal {signal_id} for shadow processing")

        # We could simulate immediately, but we need market data
        # Simulation will happen when we have both signal and market data
        # For simplicity, we'll simulate on market data update
        pass

    async def _on_market_data(self, event: MarketData):
        """Handle incoming market data event."""
        if not self._running:
            return

        # Update orderbook simulator with latest market data
        if self.orderbook_simulator:
            self.orderbook_simulator.update_orderbook(event.symbol, event)
            orderbook = self.orderbook_simulator.get_orderbook(event.symbol)
            if orderbook is None:
                logger.warning("No orderbook data for symbol %s after update", event.symbol)
                # We don't have orderbook, so we cannot simulate. Skip processing signals for this tick.
                return
        else:
            logger.warning("Orderbook simulator not available, skipping shadow fill processing")
            return

        # Check for any stored signals that we can simulate now
        # We'll simulate all recent signals (in practice, we might want to limit)
        signals_to_process = list(self.recent_signals.items())
        for signal_id, signal in signals_to_process:
            await self._simulate_and_record(signal_id, signal, orderbook)

    async def _on_fill(self, event: FillEvent):
        """Handle live fill event for comparison."""
        if not self._running:
            return

        # Try to match with a recent signal
        # We need to find a signal that corresponds to this fill
        # Since FillEvent doesn't directly reference a signal, we'll match by symbol and time
        matched_signal_id = None
        matched_signal = None
        
        for signal_id, signal in self.recent_signals.items():
            if (signal.symbol == event.symbol and 
                abs((signal.timestamp - event.timestamp).total_seconds()) < 5):  # Within 5 seconds
                matched_signal_id = signal_id
                matched_signal = signal
                break

        if matched_signal_id and matched_signal_id in self.recent_shadow_fills:
            shadow_fill = self.recent_shadow_fills[matched_signal_id]
            await self._update_metrics(event, shadow_fill)
            logger.info(f"Updated metrics for signal {matched_signal_id}")

    async def _simulate_and_record(self, signal_id: str, signal: SignalEvent, orderbook: dict):
        """Simulate order execution and record shadow fill."""
        try:
            # Simulate latency
            latency = self.latency_model.predict() if self.latency_model else 0.0
            # Simulated fill time = signal timestamp + latency
            fill_time = signal.timestamp + timedelta(seconds=latency)

            # Determine order parameters from signal
            # SignalEvent doesn't have side/quantity, we need to infer from signal_type and strength
            side = "BUY" if signal.signal_type in ["LONG", "EXIT_SHORT"] else "SELL"
            # Use strength as a proxy for quantity (in practice, this would come from position sizing)
            quantity = abs(signal.strength)  # Simplified

            # Simulate execution using orderbook
            # This is a simplified model - in reality, we'd use the orderbook simulator
            # to get fill price based on quantity and side
            # For now, we'll use a simple mid-price model
            best_bid = orderbook['bids'][0][0] if orderbook['bids'] else Decimal('0')
            best_ask = orderbook['asks'][0][0] if orderbook['asks'] else Decimal('0')
            mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else Decimal('0')
            
            slippage = self.slippage_model.calculate(
                side=side,
                quantity=quantity,
                orderbook=orderbook,
                volatility=Decimal('0.02')  # Default volatility, would come from market data in practice
            ) if self.slippage_model else Decimal('0')
            # Convert slippage to price adjustment (assuming slippage is in basis points)
            slippage_price = mid_price * (Decimal(str(slippage)) / Decimal('10000'))  # bps to decimal
            fill_price = mid_price + (slippage_price if side == "BUY" else -slippage_price)

            # Create shadow fill event
            shadow_fill = ShadowFillEvent(
                signal_id=signal_id,
                symbol=signal.symbol,
                timestamp=fill_time,
                side=side,
                quantity=quantity,
                fill_price=fill_price,
                slippage=float(slippage),  # Convert to float for storage
                latency=latency
            )

            # Store shadow fill for matching
            self.recent_shadow_fills[signal_id] = shadow_fill

            # Write to data lake
            await self._write_shadow_fill(shadow_fill)

            # Update shadow PnL (simplified)
            self.metrics["shadow_pnl"] += self._calculate_pnl(shadow_fill)

            logger.debug(f"Simulated shadow fill for signal {signal_id}")

        except Exception as e:
            logger.error(f"Error simulating shadow fill for signal {signal_id}: {e}")

    async def _write_shadow_fill(self, shadow_fill: ShadowFillEvent):
        """Write shadow fill to data lake."""
        try:
            filename = f"shadow_fills_{datetime.now().strftime('%Y%m%d')}.jsonl"
            filepath = os.path.join(self.data_lake_path, filename)
            with open(filepath, "a") as f:
                f.write(json.dumps(shadow_fill.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write shadow fill to data lake: {e}")

    async def _update_metrics(self, live_fill: FillEvent, shadow_fill: ShadowFillEvent):
        """Update metrics by comparing live and shadow fills."""
        try:
            # Slippage difference: live slippage - shadow slippage
            # We need to compute live slippage - requires expected price
            # Simplified: use midpoint at signal time? We'll approximate
            # For now, just compare fill prices
            price_diff = float(live_fill.price) - float(shadow_fill.fill_price)
            self.metrics["slippage_diff"] += price_diff

            # Execution error: difference in filled quantity
            qty_diff = abs(float(live_fill.quantity) - float(shadow_fill.quantity))
            self.metrics["execution_error"] += qty_diff

            logger.debug(f"Updated metrics: slippage_diff={price_diff}, execution_error={qty_diff}")

        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def _calculate_pnl(self, shadow_fill: ShadowFillEvent) -> float:
        """Calculate PnL for a shadow fill (simplified)."""
        # This is a placeholder - real PnL calculation would require position tracking
        return 0.0

    def get_metrics(self) -> Dict[str, float]:
        """Get current metrics."""
        return self.metrics.copy()

    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._running