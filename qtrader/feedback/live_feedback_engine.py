"""Live Feedback Engine for closing the loop between execution and strategy refinement.

This engine processes FillEvents and SignalEvents to compute:
- Trade attribution (matching fills to signals)
- Realized PnL per trade
- Slippage metrics
- Feature performance (live IC proxy)
- Strategy performance metrics

Outputs are stored in-memory as rolling windows and can be persisted to Parquet files.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional, Tuple, Any

import polars as pl

from qtrader.core.event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


@dataclass
class _SignalBufferEntry:
    """Entry in the signal buffer waiting for an entry fill."""
    signal: Any  # SignalEvent
    timestamp: datetime
    symbol: str
    strategy: str  # Strategy name
    side: str  # 'long' or 'short'
    mid_price: float
    features: Dict[str, float]


@dataclass
class _OpenTradeEntry:
    """Entry in the open trades list waiting for an exit fill."""
    signal: Any  # SignalEvent
    entry_fill: Any  # FillEvent
    entry_time: datetime
    entry_price: float
    entry_slippage: float
    symbol: str
    strategy: str
    side: str  # 'long' or 'short'
    size: float
    features: Dict[str, float]


class LiveFeedbackEngine:
    """Processes market events to generate feedback for strategy refinement.

    Attributes:
        event_bus: EventBus for publishing feedback updates.
        max_signal_age: Maximum time to keep unmatched signals in buffer.
        max_trade_age: Maximum time to keep open trades before forcing closure.
        feature_window: Maximum number of feature metrics to retain.
        strategy_window: Maximum number of strategy metrics to retain.
        execution_window: Maximum number of execution metrics to retain.
    """

    def __init__(
        self,
        event_bus: EventBus,
        max_signal_age: timedelta = timedelta(hours=1),
        max_trade_age: timedelta = timedelta(days=1),
        feature_window: int = 1000,
        strategy_window: int = 1000,
        execution_window: int = 1000,
    ) -> None:
        self.event_bus = event_bus
        self.max_signal_age = max_signal_age
        self.max_trade_age = max_trade_age
        self.feature_window = feature_window
        self.strategy_window = strategy_window
        self.execution_window = execution_window

        # Buffer for signals waiting to be matched with an entry fill
        self._signal_buffer: Deque[_SignalBufferEntry] = deque()
        # List of trades that have been entered but not exited
        self._open_trades: Deque[_OpenTradeEntry] = deque()

        # Rolling windows for metrics
        self._feature_metrics: Deque[Tuple[datetime, str, float, float, str]] = deque(
            maxlen=feature_window
        )
        self._strategy_metrics: Deque[Tuple[datetime, str, float, timedelta]] = deque(
            maxlen=strategy_window
        )
        self._execution_metrics: Deque[
            Tuple[datetime, str, str, float, Optional[float], float, float, float]
        ] = deque(maxlen=execution_window)

        logger.info(
            "LiveFeedbackEngine initialized with max_signal_age=%s, max_trade_age=%s",
            max_signal_age,
            max_trade_age,
        )

    async def process_signal(self, signal: Any) -> None:
        """Process an incoming SignalEvent.

        Args:
            signal: SignalEvent with attributes:
                symbol: str
                metadata: Dict[str, Any] containing:
                    strategy: str
                    side: str ('long' or 'short')
                    mid_price: float
                    features: Dict[str, float]
        """
        try:
            # Extract from metadata, with fallback to direct attributes for compatibility
            metadata = getattr(signal, 'metadata', {})
            strategy = metadata.get('strategy', getattr(signal, 'strategy', 'unknown'))
            side = metadata.get('side', getattr(signal, 'side', 'long'))
            mid_price = metadata.get('mid_price', getattr(signal, 'mid_price', 0.0))
            features = metadata.get('features', getattr(signal, 'features', {}))
            
            entry = _SignalBufferEntry(
                signal=signal,
                timestamp=signal.timestamp,
                symbol=signal.symbol,
                strategy=strategy,
                side=side,
                mid_price=mid_price,
                features=features,
            )
            self._signal_buffer.append(entry)
            logger.debug(
                "Buffered signal for %s %s at %s",
                signal.symbol,
                side,
                signal.timestamp,
            )
            await self._clean_signal_buffer()
        except Exception as e:
            logger.error("Error processing signal: %s", e, exc_info=True)

    async def process_fill(self, fill: Any) -> None:
        """Process an incoming FillEvent.

        Attempts to match the fill to either:
        1. An opening fill (matching signal side and fill side)
        2. An exit fill (opposite side to an open trade)

        Args:
            fill: FillEvent with attributes:
                symbol: str
                side: str ('buy' or 'sell')
                size: float
                price: float
                timestamp: datetime
        """
        print(f"DEBUG: process_fill called for {fill.symbol} {fill.side} {fill.price} at {fill.timestamp}")
        try:
            # First, try to match as an opening fill
            matched_signal_idx = self._find_matching_signal_for_entry(fill)
            print(f"DEBUG: Opening fill match result: {matched_signal_idx}")
            if matched_signal_idx is not None:
                await self._handle_entry_fill(fill, matched_signal_idx)
                return

            # If not an opening fill, try to match as an exit fill
            matched_trade_idx = self._find_matching_trade_for_exit(fill)
            print(f"DEBUG: Exit fill match result: {matched_trade_idx}")
            if matched_trade_idx is not None:
                await self._handle_exit_fill(fill, matched_trade_idx)
                return

            logger.debug(
                "Fill for %s %s at %s did not match any signal or open trade",
                fill.symbol,
                fill.side,
                fill.timestamp,
            )
        except Exception as e:
            logger.error("Error processing fill: %s", e, exc_info=True)

    def _find_matching_signal_for_entry(self, fill: Any) -> Optional[int]:
        """Find the first signal in buffer matching the fill for an entry.

        Matching criteria:
        - Same symbol
        - Same strategy
        - Signal side matches fill side (long signal -> buy fill, short signal -> sell fill)
        - Signal timestamp <= fill.timestamp
        """
        def _get_strategy_value(obj, attr_name: str = 'strategy') -> Optional[str]:
            # First try metadata
            metadata = getattr(obj, 'metadata', {})
            if isinstance(metadata, dict):
                strategy = metadata.get('strategy')
                if strategy is not None:
                    return strategy
            
            # Fallback to direct attribute
            strategy = getattr(obj, attr_name, None)
            return strategy
        
        # Extract strategy from fill
        fill_strategy = _get_strategy_value(fill)
        
        for idx, entry in enumerate(self._signal_buffer):
            # Extract strategy from signal
            signal_strategy = _get_strategy_value(entry.signal)
            
            if (
                entry.symbol == fill.symbol
                and signal_strategy == fill_strategy
                and entry.side == self._fill_side_to_signal_side(fill.side)
                and entry.timestamp <= fill.timestamp
            ):
                return idx
        return None

    def _find_matching_trade_for_exit(self, fill: Any) -> Optional[int]:
        """Find the first open trade matching the fill for an exit.

        Matching criteria:
        - Same symbol
        - Same strategy
        - Fill side is opposite to the trade's side
        """
        def _get_strategy_value(obj, attr_name: str = 'strategy') -> Optional[str]:
            # First try metadata
            metadata = getattr(obj, 'metadata', {})
            if isinstance(metadata, dict):
                strategy = metadata.get('strategy')
                if strategy is not None:
                    return strategy
            
            # Fallback to direct attribute
            strategy = getattr(obj, attr_name, None)
            return strategy
        
        for idx, trade in enumerate(self._open_trades):
            # Extract strategy from trade signal metadata or direct attribute
            trade_signal_strategy = _get_strategy_value(trade.signal)
                 
            fill_strategy = _get_strategy_value(fill)
             
            # Convert fill side to signal side for comparison
            fill_signal_side = self._fill_side_to_signal_side(fill.side)
             
            if (
                trade.symbol == fill.symbol
                and trade_signal_strategy == fill_strategy
                and self._is_opposite_side(trade.side, fill_signal_side)
            ):
                return idx
        return None

    @staticmethod
    def _fill_side_to_signal_side(fill_side: str) -> str:
        """Convert fill side to signal side convention.

        Args:
            fill_side: 'buy' or 'sell'

        Returns:
            'long' for buy, 'short' for sell
        """
        return "long" if fill_side == "buy" else "short"

    @staticmethod
    def _is_opposite_side(side1: str, side2: str) -> bool:
        """Check if two sides are opposite (long vs short)."""
        return (side1 == "long" and side2 == "short") or (side1 == "short" and side2 == "long")

    async def _handle_entry_fill(self, fill: Any, signal_idx: int) -> None:
        """Process a fill that matches a signal as an entry.

        Args:
            fill: The FillEvent representing the entry.
            signal_idx: Index of the matching signal in the buffer.
        """
        signal_entry = self._signal_buffer[signal_idx]
        # Remove the signal from the buffer
        del self._signal_buffer[signal_idx]

        # Calculate entry slippage: fill price - mid price at signal time
        entry_slippage = fill.price - signal_entry.mid_price

        # Create an open trade entry
        open_trade = _OpenTradeEntry(
            signal=signal_entry.signal,
            entry_fill=fill,
            entry_time=fill.timestamp,
            entry_price=fill.price,
            entry_slippage=entry_slippage,
            symbol=signal_entry.symbol,
            strategy=signal_entry.strategy,
            side=signal_entry.side,
            size=fill.size,
            features=signal_entry.features,
        )
        self._open_trades.append(open_trade)
        logger.info(
            "Matched entry fill for %s %s: size=%.4f, price=%.2f, slippage=%.4f",
            fill.symbol,
            fill.side,
            fill.size,
            fill.price,
            entry_slippage,
        )
        await self._clean_open_trades()

    async def _handle_exit_fill(self, fill: Any, trade_idx: int) -> None:
        """Process a fill that matches an open trade as an exit.

        Args:
            fill: The FillEvent representing the exit.
            trade_idx: Index of the matching open trade.
        """
        print(f"DEBUG: _handle_exit_fill called for fill: symbol={fill.symbol}, side={fill.side}, price={fill.price}")
        trade = self._open_trades[trade_idx]
        print(f"DEBUG: Trade details: symbol={trade.symbol}, strategy={trade.strategy}, entry_price={trade.entry_price}, size={trade.size}")
        # Remove the trade from the open trades list
        del self._open_trades[trade_idx]

        # Calculate PnL and holding time
        if trade.side == "long":
            pnl = (fill.price - trade.entry_price) * trade.size
        else:  # short
            pnl = (trade.entry_price - fill.price) * trade.size

        holding_time = fill.timestamp - trade.entry_time

        # Calculate realized return on investment
        if trade.entry_price * trade.size != 0:
            realized_return = pnl / (trade.entry_price * trade.size)
        else:
            realized_return = 0.0

        # Update feature metrics: correlate each feature value at signal time with realized return
        for feat_name, feat_val in trade.features.items():
            self._feature_metrics.append(
                (
                    fill.timestamp,
                    feat_name,
                    feat_val,
                    realized_return,
                    trade.strategy,
                )
            )

        # Update strategy metrics
        self._strategy_metrics.append(
            (
                fill.timestamp,
                trade.strategy,
                pnl,
                holding_time,
            )
        )

        # Update execution metrics
        self._execution_metrics.append(
            (
                fill.timestamp,
                trade.symbol,
                trade.strategy,
                trade.entry_slippage,
                None,  # exit slippage not available without exit signal
                trade.entry_price,
                fill.price,
                trade.size,
            )
        )

        logger.info(
            "Matched exit fill for %s %s: PnL=%.2f, return=%.4f, holding_time=%s",
            fill.symbol,
            fill.side,
            pnl,
            realized_return,
            holding_time,
        )

        # Publish feedback update event
        await self.event_bus.publish(EventType.FEEDBACK_UPDATE, None)

    async def _clean_signal_buffer(self) -> None:
        """Remove signals older than max_signal_age from the buffer."""
        cutoff = datetime.utcnow() - self.max_signal_age
        while self._signal_buffer and self._signal_buffer[0].timestamp < cutoff:
            self._signal_buffer.popleft()
            logger.debug("Removed stale signal from buffer")

    async def _clean_open_trades(self) -> None:
        """Remove open trades older than max_trade_age from the list."""
        cutoff = datetime.utcnow() - self.max_trade_age
        while self._open_trades and self._open_trades[0].entry_time < cutoff:
            self._open_trades.popleft()
            logger.debug("Removed stale open trade")

    def get_feature_metrics(self) -> pl.DataFrame:
        """Get feature performance metrics as a Polars DataFrame.

        Returns:
            DataFrame with columns: [timestamp, feature_name, feature_value, realized_return, strategy]
        """
        if not self._feature_metrics:
            return pl.DataFrame(
                schema=[
                    "timestamp",
                    "feature_name",
                    "feature_value",
                    "realized_return",
                    "strategy",
                ]
            )
        return pl.DataFrame(
            self._feature_metrics,
            schema=[
                "timestamp",
                "feature_name",
                "feature_value",
                "realized_return",
                "strategy",
            ],
        )

    def get_strategy_metrics(self) -> pl.DataFrame:
        """Get strategy performance metrics as a Polars DataFrame.

        Returns:
            DataFrame with columns: [timestamp, strategy, pnl, holding_time]
        """
        if not self._strategy_metrics:
            return pl.DataFrame(
                schema=["timestamp", "strategy", "pnl", "holding_time"]
            )
        return pl.DataFrame(
            self._strategy_metrics,
            schema=["timestamp", "strategy", "pnl", "holding_time"],
        )

    def get_execution_metrics(self) -> pl.DataFrame:
        """Get execution quality metrics as a Polars DataFrame.

        Returns:
            DataFrame with columns: [timestamp, symbol, strategy, entry_slippage, exit_slippage, entry_price, exit_price, size]
        """
        if not self._execution_metrics:
            return pl.DataFrame(
                schema=[
                    "timestamp",
                    "symbol",
                    "strategy",
                    "entry_slippage",
                    "exit_slippage",
                    "entry_price",
                    "exit_price",
                    "size",
                ]
            )
        return pl.DataFrame(
            self._execution_metrics,
            schema=[
                "timestamp",
                "symbol",
                "strategy",
                "entry_slippage",
                "exit_slippage",
                "entry_price",
                "exit_price",
                "size",
            ],
        )

    async def persist_metrics(
        self,
        feature_path: str,
        strategy_path: str,
        execution_path: str,
    ) -> None:
        """Persist metrics to Parquet files.

        Args:
            feature_path: File path for feature metrics.
            strategy_path: File path for strategy metrics.
            execution_path: File path for execution metrics.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._write_metrics, feature_path, strategy_path, execution_path
        )

    def _write_metrics(
        self,
        feature_path: str,
        strategy_path: str,
        execution_path: str,
    ) -> None:
        """Write metrics to Parquet files (runs in thread pool).

        Args:
            feature_path: File path for feature metrics.
            strategy_path: File path for strategy metrics.
            execution_path: File path for execution metrics.
        """
        try:
            feat_df = self.get_feature_metrics()
            if not feat_df.is_empty():
                feat_df.write_parquet(feature_path)
                logger.debug("Persisted feature metrics to %s", feature_path)

            strat_df = self.get_strategy_metrics()
            if not strat_df.is_empty():
                strat_df.write_parquet(strategy_path)
                logger.debug("Persisted strategy metrics to %s", strategy_path)

            exec_df = self.get_execution_metrics()
            if not exec_df.is_empty():
                exec_df.write_parquet(execution_path)
                logger.debug("Persisted execution metrics to %s", execution_path)
        except Exception as e:
            logger.error("Error persisting metrics: %s", e, exc_info=True)


# ---------------------------------------------------------------------------
# Integration snippet for qtrader/core/orchestrator.py
# ---------------------------------------------------------------------------
#
# In the __init__ method of TradingOrchestrator, after creating the event bus:
#   self.feedback_engine = LiveFeedbackEngine(
#       event_bus=self.bus,
#       max_signal_age=timedelta(hours=1),
#       max_trade_age=timedelta(days=1),
#   )
#
#   # Subscribe to events
#   self.bus.subscribe(EventType.SIGNAL, self.feedback_engine.process_signal)
#   self.bus.subscribe(EventType.FILL, self.feedback_engine.process_fill)
#
#   # Optionally, persist metrics periodically (e.g., every 5 minutes)
#   async def _persist_feedback_metrics() -> None:
#       while True:
#           await asyncio.sleep(300)  # 5 minutes
#           await self.feedback_engine.persist_metrics(
#               feature_path="reports/feature_metrics.parquet",
#               strategy_path="reports/strategy_metrics.parquet",
#               execution_path="reports/execution_metrics.parquet",
#           )
#   self._tasks.append(asyncio.create_task(_persist_feedback_metrics()))
#
# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
#
# Example unit tests (to be placed in tests/test_live_feedback_engine.py):
#
# import asyncio
# import tempfile
# from datetime import datetime, timedelta
# from unittest.mock import MagicMock
#
# import polars as pl
#
# from qtrader.feedback.live_feedback_engine import LiveFeedbackEngine
# from qtrader.core.event_bus import EventBus, EventType
#
#
# async def test_feedback_engine_basic() -> None:
#     """Test basic functionality of the feedback engine."""
#     bus = EventBus()
#     engine = LiveFeedbackEngine(
#         event_bus=bus,
#         max_signal_age=timedelta(minutes=5),
#         max_trade_age=timedelta(minutes=10),
#         feature_window=10,
#         strategy_window=10,
#         execution_window=10,
#     )
#
#     # Create a mock signal
#     signal = MagicMock()
#     signal.symbol = "AAPL"
#     signal.strategy = "momentum"
#     signal.side = "long"
#     signal.timestamp = datetime.utcnow()
#     signal.mid_price = 100.0
#     signal.features = {"rsi": 60.0, "macd": 0.5}
#
#     # Process the signal
#     await engine.process_signal(signal)
#
#     # Create a matching fill (entry)
#     fill_entry = MagicMock()
#     fill_entry.symbol = "AAPL"
#     fill_entry.side = "buy"
#     fill_entry.size = 10.0
#     fill_entry.price = 100.5  # slippage = +0.5
#     fill_entry.timestamp = signal.timestamp + timedelta(seconds=10)
#
#     # Process the entry fill
#     await engine.process_fill(fill_entry)
#
#     # Create an exit fill (opposite side)
#     fill_exit = MagicMock()
#     fill_exit.symbol = "AAPL"
#     fill_exit.side = "sell"
#     fill_exit.size = 10.0
#     fill_exit.price = 102.0  # profit
#     fill_exit.timestamp = signal.timestamp + timedelta(minutes=5)
#
#     # Process the exit fill
#     await engine.process_fill(fill_exit)
#
#     # Check metrics
#     feat_df = engine.get_feature_metrics()
#     assert feat_df.height == 2  # two features
#     assert set(feat_df["feature_name"].to_list()) == {"rsi", "macd"}
#     assert abs(feat_df["realized_return"].mean() - 0.02) < 0.001  # ~2% return
#
#     strat_df = engine.get_strategy_metrics()
#     assert strat_df.height == 1
#     assert abs(strat_df["pnl"].to_list()[0] - 20.0) < 0.001  # (102-100.5)*10 = 15? Wait: entry price 100.5, exit 102 -> 1.5*10=15
#     # Actually: for long: (exit - entry) * size = (102.0 - 100.5) * 10 = 15.0
#     assert abs(strat_df["pnl"].to_list()[0] - 15.0) < 0.001
#
#     exec_df = engine.get_execution_metrics()
#     assert exec_df.height == 1
#     assert abs(exec_df["entry_slippage"].to_list()[0] - 0.5) < 0.001
#
#     logger.info("Basic feedback engine test passed")
#
#
# if __name__ == "__main__":
#     asyncio.run(test_feedback_engine_basic())