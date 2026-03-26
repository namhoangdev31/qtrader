from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from qtrader.core.event import SignalEvent
from qtrader.ml.regime import RegimeDetector
from qtrader.strategy.meta_strategy import MetaStrategy


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

    def combine_signals(
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
        # Validate strategy signals (reuse parent validation)
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
            # Log warning in real implementation

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

        # Generate final signal based on thresholds (can be made regime-specific too)
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
                "regime_strategy_weights": self.regime_strategy_weights,
                "individual_signals": {
                    name: {
                        "signal_type": signal.signal_type,
                        "strength": signal.strength,
                    }
                    for name, signal in strategy_signals.items()
                },
            },
        )