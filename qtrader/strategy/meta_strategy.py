from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qtrader.core.event import SignalEvent

if TYPE_CHECKING:
    import polars as pl

    from qtrader.ml.regime import RegimeDetector


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
        self, strategy_signals: dict[str, SignalEvent]
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

    def _validate_signals(self, strategy_signals: dict[str, SignalEvent]) -> None:
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
        strategy_weights: dict[str, float] | None = None,
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
        self, strategy_signals: dict[str, SignalEvent]
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


@dataclass
class RegimeAwareMetaStrategy(MetaStrategy):
    """
    Meta strategy that selects/weights strategies based on detected market regime.

    Uses an existing RegimeDetector to identify the current market regime and
    then applies regime-specific strategy weights or selection logic.

    Contract:
        - Input:  dict[str, SignalEvent] from strategy layer
                  plus market data DataFrame for regime detection
        - Output: SignalEvent representing regime-adjusted combined signal
    """

    def __init__(
        self,
        regime_detector: RegimeDetector,
        regime_feature_cols: list[str],
        regime_strategy_weights: dict[int, dict[str, float]] | None = None,
        default_weights: dict[str, float] | None = None,
    ) -> None:
        """
        Initialize the regime-aware meta strategy.

        Args:
            regime_detector: Fitted RegimeDetector instance for regime identification
            regime_feature_cols: Column names to use for regime detection
            regime_strategy_weights: Mapping from regime_id to strategy weights.
                                   If None, equal weights are used for all regimes.
            default_weights: Default strategy weights when regime detection fails.
                           If None, equal weights are used.
        """
        self.regime_detector = regime_detector
        self.regime_feature_cols = regime_feature_cols
        self.regime_strategy_weights = regime_strategy_weights or {}
        self.default_weights = default_weights

    def combine_with_market_data(
        self, strategy_signals: dict[str, SignalEvent], market_data: pl.DataFrame
    ) -> SignalEvent:
        """
        Combine strategy signals with regime-based weighting.

        Args:
            strategy_signals: Dictionary mapping strategy names to their
                             SignalEvent outputs.
            market_data: Market data DataFrame for regime detection.
                       Must contain the regime_feature_cols.

        Returns:
            SignalEvent representing regime-adjusted combined signal.
        """
        # Validate strategy signals
        self._validate_signals(strategy_signals)

        # Get the symbol (same for all)
        symbol = next(iter(strategy_signals.values())).symbol

        # Detect current regime
        try:
            regime_id, confidence = self.regime_detector.current_regime_confidence(
                market_data, self.regime_feature_cols
            )
        except Exception:
            # Fallback to default weights if regime detection fails
            regime_id = -1  # Indicates fallback
            confidence = 0.0

        # Get weights for this regime
        if regime_id in self.regime_strategy_weights:
            weights = self.regime_strategy_weights[regime_id]
        elif self.default_weights is not None:
            weights = self.default_weights
        else:
            # Equal weights fallback
            weight = 1.0 / len(strategy_signals)
            weights = {name: weight for name in strategy_signals.keys()}

        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight <= 0:
            # Fallback to equal weights
            weight = 1.0 / len(strategy_signals)
            weights = {name: weight for name in strategy_signals.keys()}
            total_weight = 1.0
        
        normalized_weights = {
            name: weight / total_weight for name, weight in weights.items()
        }

        # Map signal types to numerical values
        signal_to_value = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}

        # Compute weighted sum
        weighted_sum = 0.0
        for name, signal in strategy_signals.items():
            value = signal_to_value[signal.signal_type]
            strength = signal.strength
            weight = normalized_weights.get(name, 0.0)
            weighted_sum += value * strength * weight

        # Generate final signal based on thresholds
        buy_threshold = 0.5
        sell_threshold = -0.5
        
        if weighted_sum > buy_threshold:
            signal_type = "BUY"
            strength = min(weighted_sum, 1.0)
        elif weighted_sum < sell_threshold:
            signal_type = "SELL"
            strength = min(abs(weighted_sum), 1.0)
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
                "regime_id": regime_id,
                "regime_confidence": confidence,
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
                "strategy_weights": normalized_weights,
                "individual_signals": {
                    name: {
                        "signal_type": signal.signal_type,
                        "strength": signal.strength,
                    }
                    for name, signal in strategy_signals.items()
                },
            },
        )

    def combine_signals(self, strategy_signals: dict[str, SignalEvent]) -> SignalEvent:
        """Requirement for MetaStrategy abstract class."""
        raise NotImplementedError("RegimeAwareMetaStrategy requires market_data. Use combine_with_market_data().")