"""Feedback engine for closing the loop between execution and strategy refinement."""
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np

from qtrader.core.types import (
    EventBusProtocol,
    EventType,
    FillEvent,
    SignalEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class _SignalBufferEntry:
    """Entry in the signal buffer waiting for a fill."""
    signal: SignalEvent
    timestamp: datetime
    metadata: dict[str, Any]


class FeedbackEngine:
    """
    Processes market events to generate feedback for strategy refinement and meta learning.

    Attributes:
        event_bus: EventBus for publishing feedback updates.
        max_trades: Maximum number of trades to keep in rolling windows.
        max_signal_age: Maximum time to keep unmatched signals in buffer.
    """

    def __init__(
        self,
        event_bus: EventBusProtocol,
        max_trades: int = 500,
        max_signal_age: timedelta = timedelta(hours=4),
    ) -> None:
        self.event_bus = event_bus
        self.max_trades = max_trades
        self.max_signal_age = max_signal_age
        self._signal_buffer: deque[_SignalBufferEntry] = deque()
        # Strategy returns: key -> strategy name, value -> deque of returns
        self._strategy_returns: dict[str, deque[float]] = {}
        # Feature data: key -> feature name, value -> deque of (feature_value, return)
        self._feature_data: dict[str, deque[tuple[float, float]]] = {}
        # Execution quality: slippage (absolute %) and fill ratio
        self._execution_slippages: deque[float] = deque(maxlen=max_trades)
        self._execution_fill_ratios: deque[float] = deque(maxlen=max_trades)
        # All returns for risk feedback
        self._all_returns: deque[float] = deque(maxlen=max_trades)
        self._logger = logger

    async def process_signal(self, signal: SignalEvent) -> None:
        """
        Process an incoming SignalEvent.

        Args:
            signal: SignalEvent with attributes:
                symbol: str
                metadata: Dict[str, Any] containing:
                    strategy: str
                    features: Dict[str, float]
                    expected_price: Optional[float] (mid price at signal time)
        """
        try:
            # Extract from metadata
            metadata = getattr(signal, 'metadata', {}) or {}
            strategy = metadata.get('strategy', 'unknown')
            features = metadata.get('features', {})
            expected_price = metadata.get('expected_price')

            entry = _SignalBufferEntry(
                signal=signal,
                timestamp=signal.timestamp,
                metadata={
                    'strategy': strategy,
                    'features': features,
                    'expected_price': expected_price,
                },
            )
            self._signal_buffer.append(entry)
            logger.debug(
                f"Buffered signal for {signal.symbol} {strategy} at {signal.timestamp}"
            )
            await self._clean_signal_buffer()
        except Exception as e:
            logger.error(f"Error processing signal: {e}", exc_info=True)

    async def process_fill(self, fill: FillEvent) -> None:
        """
        Process an incoming FillEvent and match it to a signal.

        Args:
            fill: FillEvent with attributes:
                symbol: str
                side: str ('BUY' or 'SELL')
                quantity: Decimal
                price: Decimal
                timestamp: datetime
        """
        try:
            # Convert fill price and quantity to Decimal for consistency (they already are)
            fill_price = fill.price
            fill_quantity = fill.quantity

            # Try to match as an opening fill (long signal -> BUY fill, short signal -> SELL fill)
            matched_signal_idx = self._find_matching_signal_for_fill(fill)
            if matched_signal_idx is not None:
                await self._handle_matched_fill(fill, matched_signal_idx, fill_price, fill_quantity)
                return

            logger.debug(
                f"Fill for {fill.symbol} {fill.side} {fill.price} at {fill.timestamp} did not match any signal"
            )
        except Exception as e:
            logger.error(f"Error processing fill: {e}", exc_info=True)

    def _find_matching_signal_for_fill(self, fill: FillEvent) -> int | None:
        """Find the first signal in buffer matching the fill for an opening trade.

        Matching criteria:
        - Same symbol
        - Signal side matches fill side (long signal -> BUY fill, short signal -> SELL fill)
        - Signal timestamp <= fill.timestamp
        """
        def _get_signal_side(signal_type: str) -> str:
            """Convert signal type to fill side convention.
            LONG -> BUY, SHORT -> SELL
            """
            if signal_type == "LONG":
                return "BUY"
            elif signal_type == "SHORT":
                return "SELL"
            else:
                return "UNKNOWN"

        for idx, entry in enumerate(self._signal_buffer):
            signal = entry.signal
            metadata = entry.metadata
            metadata.get('strategy', 'unknown')
            signal_type = signal.signal_type
            signal_side = _get_signal_side(signal_type)
            fill_side = fill.side

            if (
                entry.signal.symbol == fill.symbol
                and signal_side == fill_side
                and entry.signal.timestamp <= fill.timestamp
            ):
                return idx
        return None

    async def _handle_matched_fill(
        self,
        fill: FillEvent,
        signal_idx: int,
        fill_price: Decimal,
        fill_quantity: Decimal,
    ) -> None:
        """Process a fill that matches a signal as an opening trade.

        Args:
            fill: The FillEvent representing the fill.
            signal_idx: Index of the matching signal in the buffer.
            fill_price: The fill price as Decimal.
            fill_quantity: The fill quantity as Decimal.
        """
        signal_entry = self._signal_buffer[signal_idx]
        signal = signal_entry.signal
        metadata = signal_entry.metadata

        # Remove the signal from the buffer
        del self._signal_buffer[signal_idx]

        # Extract metadata
        strategy = metadata.get('strategy', 'unknown')
        features = metadata.get('features', {})
        expected_price = metadata.get('expected_price')

        # Calculate return and slippage if expected_price is available
        return_pct = None
        slippage_pct = None
        if expected_price is not None:
            expected_price_dec = Decimal(str(expected_price))
            if signal.signal_type == "LONG":
                return_pct = (fill_price - expected_price_dec) / expected_price_dec
                slippage_pct = (fill_price - expected_price_dec) / expected_price_dec
            elif signal.signal_type == "SHORT":
                return_pct = (expected_price_dec - fill_price) / expected_price_dec
                slippage_pct = (expected_price_dec - fill_price) / expected_price_dec
            else:
                # Unknown signal type, skip return and slippage calculation
                pass

        # Update strategy returns if we have a return
        if return_pct is not None:
            return_float = float(return_pct)
            if strategy not in self._strategy_returns:
                self._strategy_returns[strategy] = deque(maxlen=self.max_trades)
            self._strategy_returns[strategy].append(return_float)
            self._all_returns.append(return_float)
            logger.debug(
                f"Updated strategy {strategy} with return {return_float:.4f} from fill"
            )

        # Update feature data
        for feature_name, feature_value in features.items():
            try:
                feature_value_float = float(feature_value)
                if return_pct is not None:
                    return_float = float(return_pct)
                    if feature_name not in self._feature_data:
                        self._feature_data[feature_name] = deque(
                            maxlen=self.max_trades
                        )
                    self._feature_data[feature_name].append(
                        (feature_value_float, return_float)
                    )
                    logger.debug(
                        f"Updated feature {feature_name} with value {feature_value_float} and return {return_float}"
                    )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Could not process feature {feature_name} with value {feature_value}: {e}"
                )

        # Update execution quality
        if slippage_pct is not None:
            slippage_abs_pct = abs(float(slippage_pct)) * 100.0  # to percentage
            self._execution_slippages.append(slippage_abs_pct)
            logger.debug(f"Updated execution slippage: {slippage_abs_pct:.4f}%")

        # Fill ratio: we don't have intended quantity from signal, so assume 1.0 for now
        # In the future, if we have intended quantity in metadata, we can compute:
        #   fill_ratio = min(fill_quantity, intended_quantity) / intended_quantity
        self._execution_fill_ratios.append(1.0)

        # Log the matched fill
        logger.info(
            f"Matched fill for {fill.symbol} {fill.side} {fill_quantity}@{fill_price} "
            f"(strategy: {strategy}, return: {return_pct if return_pct is not None else 'N/A'})"
        )

        # Publish feedback update
        await self._publish_feedback()

    async def _clean_signal_buffer(self) -> None:
        """Remove signals older than max_signal_age from the buffer."""
        cutoff = datetime.utcnow() - self.max_signal_age
        while self._signal_buffer and self._signal_buffer[0].timestamp < cutoff:
            self._signal_buffer.popleft()
            logger.debug("Removed stale signal from buffer")

    async def _compute_ic(self, feature_data: deque[tuple[float, float]]) -> float:
        """Compute Information Coefficient (IC) as correlation between feature values and returns."""
        if len(feature_data) < 2:
            return 0.0
        values, returns = zip(*feature_data, strict=False)
        try:
            # Using numpy for correlation
            ic = np.corrcoef(values, returns)[0, 1]
            # If the correlation is undefined (e.g., constant values), return 0
            if np.isnan(ic):
                return 0.0
            return float(ic)
        except Exception as e:
            self._logger.warning(f"Error computing IC: {e}")
            return 0.0

    async def _publish_feedback(self) -> None:
        """Compute and publish feedback metrics."""
        try:
            # Strategy scores: information ratio for each strategy
            strategy_scores = {}
            for strategy, returns in self._strategy_returns.items():
                if len(returns) < 2:
                    strategy_scores[strategy] = 0.0
                else:
                    returns_array = np.array(returns)
                    mean_return = np.mean(returns_array)
                    std_return = np.std(returns_array)
                    if std_return == 0:
                        ir = 0.0
                    else:
                        ir = mean_return / std_return
                    strategy_scores[strategy] = float(ir)

            # Feature scores: IC for each feature
            feature_scores = {}
            for feature_name, feature_data in self._feature_data.items():
                ic = await self._compute_ic(feature_data)
                feature_scores[feature_name] = float(ic)

            # Execution quality: average slippage and fill ratio
            avg_slippage = (
                np.mean(self._execution_slippages)
                if len(self._execution_slippages) > 0
                else 0.0
            )
            avg_fill_ratio = (
                np.mean(self._execution_fill_ratios)
                if len(self._execution_fill_ratios) > 0
                else 1.0
            )
            execution_quality = {
                "avg_slippage": float(avg_slippage),
                "fill_ratio": float(avg_fill_ratio),
            }

            # Risk feedback: volatility and max drawdown of all returns
            if len(self._all_returns) < 2:
                return_volatility = 0.0
                max_drawdown = 0.0
            else:
                returns_array = np.array(self._all_returns)
                # Volatility: standard deviation of returns
                return_volatility = float(np.std(returns_array))
                # Max drawdown: calculate from cumulative returns
                cumulative = np.cumsum(returns_array)
                running_max = np.maximum.accumulate(cumulative)
                drawdown = (running_max - cumulative) / (running_max + 1e-9)  # avoid div by zero
                max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
            risk_feedback = {
                "return_volatility": return_volatility,
                "max_drawdown": max_drawdown,
            }

            feedback = {
                "strategy_scores": strategy_scores,
                "feature_scores": feature_scores,
                "execution_quality": execution_quality,
                "risk_feedback": risk_feedback,
            }

            # Publish feedback update
            await self.event_bus.publish(EventType.FEEDBACK_UPDATE, feedback)
            logger.debug(f"Published feedback: {feedback}")
        except Exception as e:
            logger.error(f"Error publishing feedback: {e}", exc_info=True)
            # Publish neutral feedback on error
            neutral_feedback = {
                "strategy_scores": {},
                "feature_scores": {},
                "execution_quality": {"avg_slippage": 0.0, "fill_ratio": 1.0},
                "risk_feedback": {"return_volatility": 0.0, "max_drawdown": 0.0},
            }
            await self.event_bus.publish(EventType.FEEDBACK_UPDATE, neutral_feedback)