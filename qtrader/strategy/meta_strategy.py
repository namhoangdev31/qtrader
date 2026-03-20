from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

import polars as pl

from qtrader.core.event import SignalEvent
from qtrader.strategy.strategy_layer import Strategy


@dataclass
class MetaStrategy(ABC):
    """
    Abstract base class for meta strategy layer (portfolio intelligence).

    Meta strategies combine multiple strategy signals to produce a final
    trading signal. They can apply weighting, voting, or ML aggregation.

    Contract:
        - Input:  dict[str, SignalEvent] where keys are strategy names and
                  values are SignalEvent objects from the strategy layer.
        - Output: SignalEvent representing the final combined signal.
    """

    @abstractmethod
    def combine_signals(
        self, strategy_signals: Dict[str, SignalEvent]
    ) -> SignalEvent:
        """
        Combine signals from multiple strategies into a final signal.

        Args:
            strategy_signals: Dictionary mapping strategy names to their
                             SignalEvent outputs.

        Returns:
            A SignalEvent representing the final combined signal.
        """
        pass

    def _validate_signals(self, strategy_signals: Dict[str, SignalEvent]) -> None:
        """
        Validate that all signals are for the same symbol and have valid types.

        Args:
            strategy_signals: Dictionary of strategy signals to validate

        Raises:
            ValueError: If signals are invalid
        """
        if not strategy_signals:
            raise ValueError("Strategy signals dictionary cannot be empty")

        # Check that all signals are for the same symbol
        symbols = [signal.symbol for signal in strategy_signals.values()]
        if len(set(symbols)) != 1:
            raise ValueError(
                f"All strategy signals must be for the same symbol. Got symbols: {symbols}"
            )

        # Check that all signal types are valid
        valid_types = {"BUY", "SELL", "HOLD"}
        for name, signal in strategy_signals.items():
            if signal.signal_type not in valid_types:
                raise ValueError(
                    f"Strategy '{name}' returned invalid signal type: {signal.signal_type}"
                )


class WeightedMetaStrategy(MetaStrategy):
    """
    Meta strategy that combines multiple strategies using weighted voting.

    Each strategy's signal is converted to a numerical score:
        BUY -> +1, SELL -> -1, HOLD -> 0
    The score is multiplied by the strategy's weight and the signal strength.
    The final score is summed across all strategies and thresholded to produce
    a final signal.

    Weights can be provided or default to equal weights.
    """

    def __init__(
        self,
        strategy_weights: Optional[Dict[str, float]] = None,
        buy_threshold: float = 0.5,
        sell_threshold: float = -0.5,
    ) -> None:
        """
        Initialize the weighted meta strategy.

        Args:
            strategy_weights: Weights for each strategy. If None, equal weights
                             are assigned to all provided strategies.
            buy_threshold: Threshold above which to generate BUY signal
            sell_threshold: Threshold below which to generate SELL signal
        """
        self.strategy_weights = strategy_weights
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def combine_signals(
        self, strategy_signals: Dict[str, SignalEvent]
    ) -> SignalEvent:
        """
        Combine strategy signals using weighted voting.

        Args:
            strategy_signals: Dictionary mapping strategy names to their
                             SignalEvent outputs.

        Returns:
            SignalEvent with BUY/SELL/HOLD based on weighted sum.
        """
        # Validate input signals
        self._validate_signals(strategy_signals)

        # Get the symbol (same for all)
        symbol = next(iter(strategy_signals.values())).symbol

        # Set up weights (equal if not provided)
        if self.strategy_weights is None:
            # Equal weights
            weight = 1.0 / len(strategy_signals)
            weights = {name: weight for name in strategy_signals.keys()}
        else:
            # Use provided weights, but normalize them to sum to 1.0
            total_weight = sum(self.strategy_weights.values())
            if total_weight <= 0:
                raise ValueError("Sum of strategy_weights must be positive")
            weights = {
                name: self.strategy_weights.get(name, 0.0) / total_weight
                for name in strategy_signals.keys()
            }

        # Map signal types to numerical values
        signal_to_value = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}

        # Compute weighted sum
        weighted_sum = 0.0
        for name, signal in strategy_signals.items():
            value = signal_to_value[signal.signal_type]
            strength = signal.strength
            weight = weights[name]
            weighted_sum += value * strength * weight

        # Generate final signal based on thresholds
        if weighted_sum > self.buy_threshold:
            signal_type = "BUY"
            strength = min(weighted_sum, 1.0)  # Cap strength at 1.0
        elif weighted_sum < self.sell_threshold:
            signal_type = "SELL"
            strength = min(abs(weighted_sum), 1.0)  # Cap strength at 1.0
        else:
            signal_type = "HOLD"
            strength = 0.0

        # Create and return SignalEvent
        return SignalEvent(
            symbol=symbol,
            signal_type=signal_type,
            strength=strength,
            metadata={
                "weighted_sum": weighted_sum,
                "buy_threshold": self.buy_threshold,
                "sell_threshold": self.sell_threshold,
                "strategy_weights": weights,
                "individual_signals": {
                    name: {
                        "signal_type": signal.signal_type,
                        "strength": signal.strength,
                    }
                    for name, signal in strategy_signals.items()
                },
            },
        )