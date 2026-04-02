"""Ensemble strategy combiner that combines multiple strategies with dynamic weighting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import polars as pl

from qtrader.core.types import SignalEvent, ValidatedFeatures

# Try to import MetaLearningEngine, create a fallback if not available
# Try to import MetaLearningEngine, create a fallback if not available
try:
    from qtrader.ml.meta_learning_engine import MetaLearningEngine
except ImportError:
    # Fallback when ML dependencies are not available
    MetaLearningEngine = None  # type: ignore

from qtrader.core.container import container

_LOG = container.get("logger")


class EnsembleStrategy:
    """
    Ensemble strategy that combines multiple strategies with dynamic weighting.
    
    This strategy:
    - Takes multiple sub-strategies (that have a compute_signals method)
    - Combines their signals using weighted voting
    - Dynamically adjusts weights based on recent performance via meta-learning
    - Can incorporate regime detection for context-aware weighting
    """

    def __init__(
        self,
        strategies: list,
        performance_window: int = 20,
        min_weight: float = 0.05,
        max_weight: float = 0.5,
        rebalance_frequency: int = 5,
        enable_meta_learning: bool = True,
        meta_learning_window: int = 50,
        meta_learning_min_trades: int = 10,
    ) -> None:
        """
        Initialize the ensemble strategy.
        
        Args:
            strategies: List of sub-strategies to combine (each must have a compute_signals method)
            performance_window: Window for performance evaluation
            min_weight: Minimum weight per strategy
            max_weight: Maximum weight per strategy
            rebalance_frequency: How often to rebalance weights (in signals)
            enable_meta_learning: Whether to use meta-learning for weight adjustment
            meta_learning_window: Window size for meta-learning performance memory
            meta_learning_min_trades: Minimum trades required for meta-learning updates
        """
        self.strategies = strategies
        self.performance_window = performance_window
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.rebalance_frequency = rebalance_frequency
        self.enable_meta_learning = enable_meta_learning
        
        # Initialize meta-learning engine if enabled and available
        if self.enable_meta_learning and MetaLearningEngine is not None:
            self.meta_learning_engine = MetaLearningEngine(
                window_size=meta_learning_window,
                min_trades=meta_learning_min_trades,
                temperature=1.0,
                strategy_weights=(0.4, 0.3, 0.2, 0.1),  # weights for sharpe, pnl_mean, drawdown, hit_ratio
                decay_penalty=0.5,
                min_weight=min_weight,
                max_weight=max_weight,
            )
        else:
            self.meta_learning_engine = None

        # Legacy performance tracking (kept for backward compatibility)
        self._strategy_performance: dict[int, list[float]] = {
            i: [] for i in range(len(strategies))
        }
        self._strategy_weights: dict[int, float] = {
            i: 1.0 / len(strategies) for i in range(len(strategies))
        }
        self._signal_count = 0
        
        # Current regime information (to be updated externally)
        self._current_regime: str | None = None
        self._regime_probability: float = 0.0

    def update_regime_info(self, regime: str, regime_prob: float) -> None:
        """Update current regime information for meta-learning."""
        self._current_regime = regime
        self._regime_probability = regime_prob
        
        if self.meta_learning_engine:
            self.meta_learning_engine.update_regime_info(regime, regime_prob)

    def compute_signals(self, features: dict[str, pl.Series]) -> SignalEvent:
        """
        Compute signals by combining outputs from all sub-strategies.
        
        Args:
            features: Dictionary mapping alpha names to their feature series
            
        Returns:
            SignalEvent containing combined signal and metadata
        """
        # Handle empty strategies list
        if not self.strategies:
            return SignalEvent(
                symbol="UNKNOWN",
                timestamp=datetime.utcnow(),
                signal_type="HOLD",
                strength=Decimal('0.0'),
                metadata={}
            )
        
        # Get signals from each strategy
        strategy_signals = {}
        for i, strategy in enumerate(self.strategies):
            try:
                # Use compute_signals from the strategy (not generate_signal)
                signal = strategy.compute_signals(features)
                strategy_signals[i] = signal
            except Exception as e:
                _LOG.error(f"Error computing signal for strategy {i}: {e}")
                # Create a neutral signal on error
                strategy_signals[i] = SignalEvent(
                    symbol="UNKNOWN",
                    timestamp=datetime.utcnow(),
                    signal_type="HOLD",
                    strength=Decimal('0.0'),
                    metadata={}
                )
        
        # Update performance tracking for each strategy (legacy)
        self._update_performance(strategy_signals)
        
        # Rebalance weights if needed (legacy method)
        self._signal_count += 1
        if self._signal_count % self.rebalance_frequency == 0:
            self._rebalance_weights()
        
        # Get weights: either from meta-learning or legacy system
        if self.enable_meta_learning and self.meta_learning_engine:
            weights_dict = self.meta_learning_engine.get_weights()
            strategy_weights = weights_dict.get("strategy_weights")
            if not isinstance(strategy_weights, dict):
                strategy_weights = {}
            # Convert strategy names to indices for compatibility
            current_weights = {
                i: strategy_weights.get(self._get_strategy_name(i), 0.0) 
                for i in range(len(self.strategies))
            }
            # If no weights from meta-learning, fall back to legacy weights
            if not any(strategy_weights.values()):
                current_weights = self._strategy_weights.copy()
        else:
            current_weights = self._strategy_weights.copy()
        
        # Normalize weights to sum to 1.0
        weight_sum = sum(current_weights.values())
        if weight_sum > 0:
            normalized_weights = {k: v / weight_sum for k, v in current_weights.items()}
        else:
            # Equal weights fallback
            equal_weight = 1.0 / len(self.strategies)
            normalized_weights = {i: equal_weight for i in range(len(self.strategies))}
        
        # Combine signals using current weights
        combined_signal = self._combine_signals(strategy_signals, normalized_weights)
        
        # Create ensemble signal event
        ensemble_signal = SignalEvent(
            symbol="UNKNOWN",
            timestamp=datetime.utcnow(),
            signal_type="ENSEMBLE",
            strength=float(combined_signal.get('strength', 0.0)),
            metadata={
                'buy_prob': combined_signal.get('buy_prob', 0.0),
                'sell_prob': combined_signal.get('sell_prob', 0.0),
                'hold_prob': combined_signal.get('hold_prob', 0.0),
                'strategy_weights': normalized_weights,
                'signal_components': {
                    i: {
                        'signal_type': sig.signal_type,
                        'strength': float(sig.strength),
                        'metadata': sig.metadata
                    } for i, sig in strategy_signals.items()
                }
            }
        )
        
        return ensemble_signal

    def _get_strategy_name(self, index: int) -> str:
        """Get strategy name from index (fallback to string representation)."""
        strategy = self.strategies[index]
        if hasattr(strategy, '__class__'):
            return strategy.__class__.__name__
        return str(strategy)

    def _update_performance(self, strategy_signals: dict) -> None:
        """Update performance tracking for each strategy based on their signals."""
        # In a real implementation, we would wait for fill signals to update performance
        # For now, we'll use a proxy: the strength of the signal as a proxy for confidence
        # This is a simplification - production would use actual P&L from fills
        
        for i, signal in strategy_signals.items():
            if i not in self._strategy_performance:
                self._strategy_performance[i] = []
            
            # Use signal strength as a proxy for performance (higher strength = better signal)
            # In production, replace with actual P&L from fills
            performance_proxy = float(signal.strength)
            self._strategy_performance[i].append(performance_proxy)
            
            # Keep only the recent window
            if len(self._strategy_performance[i]) > self.performance_window:
                self._strategy_performance[i] = self._strategy_performance[i][-self.performance_window:]

    def _rebalance_weights(self) -> None:
        """Rebalance strategy weights based on recent performance (legacy method)."""
        # Calculate average performance for each strategy
        avg_performance = {}
        for i, performance_list in self._strategy_performance.items():
            if performance_list:
                avg_performance[i] = sum(performance_list) / len(performance_list)
            else:
                avg_performance[i] = 0.0
        
        # If all performances are zero or negative, fall back to equal weights
        if all(p <= 0 for p in avg_performance.values()):
            equal_weight = 1.0 / len(self.strategies)
            for i in range(len(self.strategies)):
                self._strategy_weights[i] = equal_weight
            return
        
        # Weight strategies by their performance (softmax-like)
        # Shift performances to be positive for softmax
        min_perf = min(avg_performance.values())
        shifted_perf = {
            i: perf - min_perf + 1e-8  # Add small epsilon to avoid zero
            for i, perf in avg_performance.items()
        }
        
        total_shifted = sum(shifted_perf.values())
        if total_shifted > 0:
            raw_weights = {
                i: perf / total_shifted
                for i, perf in shifted_perf.items()
            }
        else:
            # Fall back to equal weights
            equal_weight = 1.0 / len(self.strategies)
            raw_weights = {i: equal_weight for i in range(len(self.strategies))}
        
        # Apply min/max constraints
        constrained_weights = {}
        for i, weight in raw_weights.items():
            if weight < self.min_weight:
                constrained_weights[i] = self.min_weight
            elif weight > self.max_weight:
                constrained_weights[i] = self.max_weight
            else:
                constrained_weights[i] = weight
        
        # Renormalize to sum to 1.0
        weight_sum = sum(constrained_weights.values())
        if weight_sum > 0:
            for i in range(len(self.strategies)):
                self._strategy_weights[i] = constrained_weights[i] / weight_sum
        else:
            # Fall back to equal weights
            equal_weight = 1.0 / len(self.strategies)
            for i in range(len(self.strategies)):
                self._strategy_weights[i] = equal_weight
        
        _LOG.debug(f"Rebalanced ensemble weights: {self._strategy_weights}")

    def _combine_signals(self, strategy_signals: dict, weights: dict[int, float]) -> dict:
        """Combine signals from all strategies using current weights."""
        # Initialize combined signal components
        buy_prob = 0.0
        sell_prob = 0.0
        hold_prob = 0.0
        
        # Map strategy indices to their weights
        for i, signal in strategy_signals.items():
            weight = weights.get(i, 0.0)
            
            # Extract signal probabilities
            buy_prob += weight * signal.metadata.get('buy_prob', 0.0)
            sell_prob += weight * signal.metadata.get('sell_prob', 0.0)
            hold_prob += weight * signal.metadata.get('hold_prob', 0.0)
        
        # Normalize the combined probabilities
        total_prob = buy_prob + sell_prob + hold_prob
        if total_prob > 0:
            buy_prob /= total_prob
            sell_prob /= total_prob
            hold_prob /= total_prob
        else:
            # Uniform distribution if no signal
            buy_prob = sell_prob = hold_prob = 1.0 / 3.0
        
        # Calculate strength as deviation from uniform distribution
        uniform_prob = 1.0 / 3.0
        strength = max(0.0, max(buy_prob, sell_prob, hold_prob) - uniform_prob) * 1.5  # Scale to [0, 1]
        
        return {
            'buy_prob': buy_prob,
            'sell_prob': sell_prob,
            'hold_prob': hold_prob,
            'strength': strength
        }

    async def generate_signal(self, validated_features: ValidatedFeatures) -> SignalEvent:
        """
        Generate a trading signal from validated features.
        
        This method adapts the ValidatedFeatures to the format expected by compute_signals.
        
        Args:
            validated_features: Validated features containing the latest feature values
            
        Returns:
            SignalEvent containing the trading signal
        """
        # Convert validated_features.features (Dict[str, Decimal]) to a dict of pl.Series of length 1
        features_dict = {}
        for name, value in validated_features.features.items():
            features_dict[name] = pl.Series([value])  # length 1 series
        return self.compute_signals(features_dict)