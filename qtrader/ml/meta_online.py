"""Online meta-learning engine for dynamic strategy and feature weighting."""
import math
from typing import Any, Dict, Optional, Tuple

import numpy as np

from qtrader.core.types import EventBusProtocol


class OnlineMetaLearner:
    """
    Dynamically adjusts strategy weights, feature weights, and risk multiplier based on feedback.

    Attributes:
        regime_states: Dictionary mapping regime to its state (strategy_weights, feature_weights, risk_multiplier).
        alpha: Exponential decay factor for weight updates (2/(n_memory+1)).
        strategy_min_weight: Minimum allowed weight for any strategy.
        strategy_max_weight: Maximum allowed weight for any strategy.
        feature_min_weight: Minimum allowed weight for any feature.
        feature_max_weight: Maximum allowed weight for any feature.
        ic_threshold: Minimum IC for a feature to receive positive weight.
        temperature: Temperature parameter for softmax in strategy weight calculation.
    """

    def __init__(
        self,
        n_memory: int = 100,
        strategy_min_weight: float = 0.01,
        strategy_max_weight: float = 0.50,
        feature_min_weight: float = 0.01,
        feature_max_weight: float = 0.50,
        ic_threshold: float = 0.02,
        temperature: float = 1.0,
    ) -> None:
        """
        Initialize the online meta-learner.

        Args:
            n_memory: Number of steps to remember for exponential decay (default 100).
            strategy_min_weight: Minimum weight per strategy after clamping.
            strategy_max_weight: Maximum weight per strategy after clamping.
            feature_min_weight: Minimum weight per feature after clamping.
            feature_max_weight: Maximum weight per feature after clamping.
            ic_threshold: Minimum information coefficient for a feature to be considered.
            temperature: Temperature for softmax scaling of strategy scores.
        """
        self.regime_states: Dict[Any, Dict[str, Any]] = {}
        self.alpha = 2.0 / (n_memory + 1)  # Exponential decay factor
        self.strategy_min_weight = strategy_min_weight
        self.strategy_max_weight = strategy_max_weight
        self.feature_min_weight = feature_min_weight
        self.feature_max_weight = feature_max_weight
        self.ic_threshold = ic_threshold
        self.temperature = temperature

    def _get_initial_state(self) -> Dict[str, Any]:
        """Return the initial state for a new regime."""
        return {
            'strategy_weights': {},
            'feature_weights': {},
            'risk_multiplier': 1.0
        }

    def _compute_suggested_strategy_weights(self, feedback: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute suggested strategy weights from feedback using softmax of information ratios.

        Args:
            feedback: Feedback dictionary from FeedbackEngine.

        Returns:
            Dictionary mapping strategy names to suggested weights (before normalization).
        """
        strategy_scores = feedback.get('strategy_scores', {})
        if not strategy_scores:
            return {}
        # Apply softmax with temperature for numerical stability
        max_score = max(strategy_scores.values())
        exp_scores = {
            s: math.exp((score - max_score) / self.temperature)
            for s, score in strategy_scores.items()
        }
        total = sum(exp_scores.values())
        if total == 0:
            # Fallback to uniform if all scores are equal after shifting
            return {s: 1.0 / len(strategy_scores) for s in strategy_scores}
        return {s: exp_score / total for s, exp_score in exp_scores.items()}

    def _compute_suggested_feature_weights(self, feedback: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute suggested feature weights from feedback based on IC scores.

        Args:
            feedback: Feedback dictionary from FeedbackEngine.

        Returns:
            Dictionary mapping feature names to suggested weights (before normalization).
        """
        feature_scores = feedback.get('feature_scores', {})
        raw_weights = {}
        for feature, ic in feature_scores.items():
            weight = max(0.0, ic - self.ic_threshold)
            raw_weights[feature] = weight
        total = sum(raw_weights.values())
        if total > 0:
            return {f: w / total for f, w in raw_weights.items()}
        else:
            # Fallback to uniform if no feature passes the threshold
            if feature_scores:
                uniform = 1.0 / len(feature_scores)
                return {f: uniform for f in feature_scores}
            return {}

    def _compute_suggested_risk_multiplier(self, feedback: Dict[str, Any]) -> float:
        """
        Compute suggested risk multiplier from feedback based on drawdown.

        Args:
            feedback: Feedback dictionary from FeedbackEngine.

        Returns:
            Suggested risk multiplier (a float).
        """
        risk_feedback = feedback.get('risk_feedback', {})
        max_drawdown = risk_feedback.get('max_drawdown', 0.0)
        # Higher drawdown leads to lower risk multiplier (more conservative)
        # Formula: multiplier = 1 / (1 + k * drawdown), k=10 for sensitivity
        return 1.0 / (1.0 + max_drawdown * 10.0)

    def _update_weights(
        self,
        current_weights: Dict[str, float],
        suggested_weights: Dict[str, float],
        min_weight: float,
        max_weight: float,
    ) -> Dict[str, float]:
        """
        Update weights using exponential moving average, safety jump limits, and renormalization.

        Args:
            current_weights: Current weights dictionary.
            suggested_weights: Suggested weights dictionary from feedback.
            min_weight: Minimum allowed weight after clamping.
            max_weight: Maximum allowed weight after clamping.

        Returns:
            Updated and normalized weights dictionary.
        """
        all_keys = set(current_weights.keys()) | set(suggested_weights.keys())
        new_weights = {}
        for key in all_keys:
            cw = current_weights.get(key, 0.0)
            sw = suggested_weights.get(key, 0.0)
            # Exponential moving average
            raw_new = (1 - self.alpha) * cw + self.alpha * sw
            # Safety jump limit: prevent change >20% of current weight
            change = raw_new - cw
            if cw == 0.0:
                # Allow small absolute change when current weight is zero
                max_change = 0.02
            else:
                max_change = 0.2 * abs(cw)
            if abs(change) > max_change:
                change = math.copysign(min(abs(change), max_change), change)
                new_weight = cw + change
            else:
                new_weight = raw_new
            # Clamp to [min_weight, max_weight]
            new_weight = max(min_weight, min(max_weight, new_weight))
            new_weights[key] = new_weight
        # Renormalize to sum to 1
        total = sum(new_weights.values())
        if total > 0:
            for key in new_weights:
                new_weights[key] /= total
        else:
            # If total is zero, assign uniform weight across all keys
            if all_keys:
                uniform = 1.0 / len(all_keys)
                for key in new_weights:
                    new_weights[key] = uniform
            else:
                # No keys, return empty dict
                pass
        return new_weights

    def _update_strategy_weights(self, state: Dict[str, Any], feedback: Dict[str, Any]) -> None:
        """Update strategy weights in the given state based on feedback."""
        suggested = self._compute_suggested_strategy_weights(feedback)
        state['strategy_weights'] = self._update_weights(
            state['strategy_weights'],
            suggested,
            self.strategy_min_weight,
            self.strategy_max_weight
        )

    def _update_feature_weights(self, state: Dict[str, Any], feedback: Dict[str, Any]) -> None:
        """Update feature weights in the given state based on feedback."""
        suggested = self._compute_suggested_feature_weights(feedback)
        state['feature_weights'] = self._update_weights(
            state['feature_weights'],
            suggested,
            self.feature_min_weight,
            self.feature_max_weight
        )

    def _update_risk_multiplier(self, state: Dict[str, Any], feedback: Dict[str, Any]) -> None:
        """Update risk multiplier in the given state based on feedback."""
        current = state['risk_multiplier']
        suggested = self._compute_suggested_risk_multiplier(feedback)
        # Exponential moving average
        raw_new = (1 - self.alpha) * current + self.alpha * suggested
        # Safety jump limit
        change = raw_new - current
        if current == 0.0:
            max_change = 0.02
        else:
            max_change = 0.2 * abs(current)
        if abs(change) > max_change:
            change = math.copysign(min(abs(change), max_change), change)
            new_risk = current + change
        else:
            new_risk = raw_new
        # Clamp to reasonable bounds [0.5, 2.0]
        new_risk = max(0.5, min(2.0, new_risk))
        state['risk_multiplier'] = new_risk

    def update(self, feedback: Dict[str, Any], regime: Any) -> Dict[str, Any]:
        """
        Update the meta-learner state for a given regime and return the current weights.

        Args:
            feedback: Feedback dictionary from FeedbackEngine.
            regime: Regime identifier (e.g., string or integer from RegimeDetector).

        Returns:
            Dictionary with keys:
                - strategy_weights: dict[str, float]
                - feature_weights: dict[str, float]
                - risk_multiplier: float
            Returns the current state for the regime on error to avoid crashing.
        """
        try:
            if regime not in self.regime_states:
                self.regime_states[regime] = self._get_initial_state()
            state = self.regime_states[regime]

            self._update_strategy_weights(state, feedback)
            self._update_feature_weights(state, feedback)
            self._update_risk_multiplier(state, feedback)

            return {
                'strategy_weights': state['strategy_weights'].copy(),
                'feature_weights': state['feature_weights'].copy(),
                'risk_multiplier': state['risk_multiplier']
            }
        except Exception as e:
            # Log the error and return the current state for the regime to avoid crashing
            # In a real system, we would use a proper logger; here we use print for simplicity.
            print(f"Error in OnlineMetaLearner.update: {e}")
            if regime in self.regime_states:
                state = self.regime_states[regime]
                return {
                    'strategy_weights': state['strategy_weights'].copy(),
                    'feature_weights': state['feature_weights'].copy(),
                    'risk_multiplier': state['risk_multiplier']
                }
            else:
                # Return neutral state if regime not found
                return {
                    'strategy_weights': {},
                    'feature_weights': {},
                    'risk_multiplier': 1.0
                }