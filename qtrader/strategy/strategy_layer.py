from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import polars as pl

from qtrader.core.event import SignalEvent


@dataclass
class Strategy(ABC):
    """
    Base class for strategy layer (decision engine).

    Strategies take in multiple alpha features and output discrete trading signals
    (BUY/SELL/HOLD). This is a pure decision engine that combines features
    but does not perform feature engineering itself.

    Contract:
        - Input:  dict[str, pl.Series] where keys are alpha names and values are
                  feature series (normalized, continuous values from Alpha layer)
        - Output: SignalEvent with signal_type in ["BUY", "SELL", "HOLD"] and
                  strength representing conviction
    """

    # Define the signal types this strategy can emit
    SIGNAL_TYPES: ClassVar[list[str]] = ["BUY", "SELL", "HOLD"]

    @abstractmethod
    def compute_signals(
        self, features: dict[str, pl.Series]
    ) -> SignalEvent:
        """
        Compute trading signals from alpha features.

        This method must be implemented by subclasses to return a trading signal.

        Args:
            features: Dictionary mapping alpha names to their feature series.
                     Each series should be normalized and continuous.

        Returns:
            A SignalEvent with signal_type in ["BUY", "SELL", "HOLD"].
        """
        pass

    def _validate_features(self, features: dict[str, pl.Series]) -> None:
        """
        Validate that all feature series have the same length and are Float64.

        Args:
            features: Dictionary of alpha features to validate

        Raises:
            ValueError: If features are invalid
        """
        if not features:
            raise ValueError("Features dictionary cannot be empty")

        # Check that all series have the same length
        lengths = [series.len() for series in features.values()]
        if len(set(lengths)) != 1:
            raise ValueError(
                f"All feature series must have the same length. Got lengths: {lengths}"
            )

        # Check that all series are Float64
        for name, series in features.items():
            if series.dtype != pl.Float64:
                raise ValueError(
                    f"Feature '{name}' must be Float64, got {series.dtype}"
                )


class RuleBasedStrategy(Strategy):
    """
    Simple rule-based strategy that combines alpha features with weights.

    This strategy computes a weighted sum of normalized alpha features and
    generates signals based on thresholds:
        - Weighted sum >  BUY_THRESHOLD  -> BUY
        - Weighted sum < -SELL_THRESHOLD -> SELL
        - Otherwise                       -> HOLD
    """

    def __init__(
        self,
        alpha_weights: dict[str, float] | None = None,
        buy_threshold: float = 0.5,
        sell_threshold: float = 0.5,
    ) -> None:
        """
        Initialize the rule-based strategy.

        Args:
            alpha_weights: Weights for each alpha feature. If None, equal weights
                          are assigned to all provided features.
            buy_threshold: Threshold above which to generate BUY signal
            sell_threshold: Threshold below which to generate SELL signal
        """
        self.alpha_weights = alpha_weights
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def compute_signals(
        self, features: dict[str, pl.Series]
    ) -> SignalEvent:
        """
        Compute trading signals using weighted sum of alpha features.

        Args:
            features: Dictionary mapping alpha names to their feature series

        Returns:
            SignalEvent with BUY/SELL/HOLD signal
        """
        # Validate input features
        self._validate_features(features)

        # Set up weights (equal if not provided)
        if self.alpha_weights is None:
            # Equal weights
            weight = 1.0 / len(features)
            weights = {name: weight for name in features.keys()}
        else:
            # Use provided weights, but normalize them to sum to 1.0
            total_weight = sum(self.alpha_weights.values())
            if total_weight <= 0:
                raise ValueError("Sum of alpha_weights must be positive")
            weights = {
                name: self.alpha_weights.get(name, 0.0) / total_weight
                for name in features.keys()
            }

        # Compute weighted sum of features
        # Start with zeros series of correct length
        first_series = next(iter(features.values()))
        weighted_sum = pl.Series(
            [0.0] * first_series.len(), dtype=pl.Float64
        ).alias("weighted_sum")

        # Add each weighted feature
        for name, series in features.items():
            weight = weights[name]
            weighted_sum = weighted_sum + (series * weight)

        # For simplicity, we'll use the last value of the weighted sum
        # In practice, you might want to use a different aggregation method
        latest_value = weighted_sum[-1]

        # Generate signal based on thresholds
        if latest_value > self.buy_threshold:
            signal_type = "BUY"
            strength = min(latest_value, 1.0)  # Cap strength at 1.0
        elif latest_value < -self.sell_threshold:
            signal_type = "SELL"
            strength = min(abs(latest_value), 1.0)  # Cap strength at 1.0
        else:
            signal_type = "HOLD"
            strength = 0.0

        # Create and return SignalEvent
        return SignalEvent(
            symbol="UNKNOWN",  # This should be set by the caller/context
            signal_type=signal_type,
            strength=strength,
            metadata={
                "weighted_sum": float(latest_value),
                "buy_threshold": self.buy_threshold,
                "sell_threshold": self.sell_threshold,
                "alpha_weights": weights,
            },
        )