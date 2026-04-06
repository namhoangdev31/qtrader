"""
Meta-learning engine for dynamic strategy and feature weight adjustment.
"""

from collections import deque

import numpy as np


class MetaLearningEngine:
    """
    Online meta-learning engine to dynamically adjust:
    - Strategy weights
    - Feature importance
    - Signal confidence scaling
    """

    def __init__(  # noqa: PLR0913
        self,
        window_size: int = 50,
        min_trades: int = 10,
        temperature: float = 1.0,
        strategy_weights: tuple[float, float, float, float] = (0.4, 0.3, 0.2, 0.1),
        decay_penalty: float = 0.5,
        min_weight: float = 0.01,
        max_weight: float = 0.50,
    ) -> None:
        """
        Initialize meta-learning engine.

        Args:
            window_size: Rolling window size for performance memory
            min_trades: Minimum trades required for weight updates
            temperature: Temperature for softmax weighting
            strategy_weights: Weights for (sharpe, pnl_mean, drawdown, hit_ratio)
                in score calculation
            decay_penalty: Penalty factor for feature decay
            min_weight: Minimum weight after clipping
            max_weight: Maximum weight after clipping
        """
        self.window_size = window_size
        self.min_trades = min_trades
        self.temperature = temperature
        self.w_sharpe, self.w_pnl, self.w_dd, self.w_hit = strategy_weights
        self.decay_penalty = decay_penalty
        self.min_weight = min_weight
        self.max_weight = max_weight

        # Performance memory: global and per-regime
        self.global_strategy_history: dict[str, deque[tuple[float, float, float, float]]] = {}
        self.global_feature_history: dict[str, deque[tuple[float, float]]] = {}
        self.regime_strategy_history: dict[
            str, dict[str, deque[tuple[float, float, float, float]]]
        ] = {}
        self.regime_feature_history: dict[str, dict[str, deque[tuple[float, float]]]] = {}

        # Current regime info
        self.current_regime: str | None = None
        self.regime_probability: float = 0.0

    def update(
        self,
        strategy_performance: dict[str, dict[str, float]],
        feature_performance: dict[str, tuple[float, float]],
        regime: str,
        regime_prob: float,
        current_allocations: dict[str, float] | None = None,
    ) -> None:
        """
        Update performance memory with latest metrics.

        Args:
            strategy_performance: Dict mapping strategy name to metrics dict
                with keys: 'sharpe', 'pnl_mean', 'drawdown', 'hit_ratio'
            feature_performance: Dict mapping feature name to (IC, decay) tuple
            regime: Current market regime label
            regime_prob: Probability of current regime (0-1)
            current_allocations: Current strategy allocations (optional, for initialization)
        """
        self.current_regime = regime
        self.regime_probability = regime_prob

        # Update global history
        for strategy, metrics in strategy_performance.items():
            if strategy not in self.global_strategy_history:
                self.global_strategy_history[strategy] = deque(maxlen=self.window_size)
            self.global_strategy_history[strategy].append(
                (metrics["sharpe"], metrics["pnl_mean"], metrics["drawdown"], metrics["hit_ratio"])
            )

        for feature, (ic, decay) in feature_performance.items():
            if feature not in self.global_feature_history:
                self.global_feature_history[feature] = deque(maxlen=self.window_size)
            self.global_feature_history[feature].append((ic, decay))

        # Update regime-specific history
        if regime not in self.regime_strategy_history:
            self.regime_strategy_history[regime] = {}
        if regime not in self.regime_feature_history:
            self.regime_feature_history[regime] = {}

        for strategy, metrics in strategy_performance.items():
            if strategy not in self.regime_strategy_history[regime]:
                self.regime_strategy_history[regime][strategy] = deque(maxlen=self.window_size)
            self.regime_strategy_history[regime][strategy].append(
                (metrics["sharpe"], metrics["pnl_mean"], metrics["drawdown"], metrics["hit_ratio"])
            )

        for feature, (ic, decay) in feature_performance.items():
            if feature not in self.regime_feature_history[regime]:
                self.regime_feature_history[regime][feature] = deque(maxlen=self.window_size)
            self.regime_feature_history[regime][feature].append((ic, decay))

    def update_regime_info(self, regime: str, regime_prob: float) -> None:
        """Update regime information without updating performance history."""
        self.current_regime = regime
        self.regime_probability = regime_prob

    def _compute_strategy_scores(
        self, history: dict[str, deque[tuple[float, float, float, float]]]
    ) -> dict[str, float]:
        """Compute strategy scores from history."""
        scores = {}
        for strategy, hist in history.items():
            if len(hist) < self.min_trades:
                scores[strategy] = 0.0
                continue

            # Calculate average metrics over window.
            sharpe_avg = float(np.mean([x[0] for x in hist]))
            pnl_mean_avg = float(np.mean([x[1] for x in hist]))
            drawdown_avg = float(np.mean([x[2] for x in hist]))
            hit_ratio_avg = float(np.mean([x[3] for x in hist]))

            # Compute score: w1*sharpe + w2*pnl_mean - w3*drawdown + w4*hit_ratio
            score = (
                self.w_sharpe * sharpe_avg
                + self.w_pnl * pnl_mean_avg
                - self.w_dd * drawdown_avg
                + self.w_hit * hit_ratio_avg
            )
            scores[strategy] = score
        return scores

    def _compute_feature_scores(
        self, history: dict[str, deque[tuple[float, float]]]
    ) -> dict[str, float]:
        """Compute feature scores from history."""
        scores = {}
        for feature, hist in history.items():
            if len(hist) < self.min_trades:
                scores[feature] = 0.0
                continue

            ic_avg = float(np.mean([x[0] for x in hist]))
            decay_avg = float(np.mean([x[1] for x in hist]))
            score = ic_avg - self.decay_penalty * decay_avg
            scores[feature] = score
        return scores

    def _softmax(self, scores: dict[str, float]) -> dict[str, float]:
        """Apply softmax to scores."""
        if not scores:
            return {}

        # Handle case where all scores are zero or insufficient data
        if all(v == 0 for v in scores.values()):
            n = len(scores)
            return {k: 1.0 / n for k in scores}

        # Shift for numerical stability
        max_score = max(scores.values())
        exp_scores = {k: np.exp((v - max_score) / self.temperature) for k, v in scores.items()}
        sum_exp = sum(exp_scores.values())
        return {k: v / sum_exp for k, v in exp_scores.items()}

    def _clip_and_normalize(self, weights: dict[str, float]) -> dict[str, float]:
        """Clip weights to bounds and renormalize."""
        clipped = {k: max(self.min_weight, min(self.max_weight, v)) for k, v in weights.items()}
        total = sum(clipped.values())
        if total == 0:
            n = len(clipped)
            return {k: 1.0 / n for k in clipped}
        return {k: v / total for k, v in clipped.items()}

    def _average_sharpe(
        self, history: dict[str, deque[tuple[float, float, float, float]]]
    ) -> float:
        """Calculate average Sharpe across all strategies."""
        sharpes = []
        for hist in history.values():
            if hist:
                sharpes.extend([x[0] for x in hist])
        return float(np.mean(sharpes)) if sharpes else 0.0

    def _sigmoid(self, x: float) -> float:
        """Sigmoid function."""
        return 1.0 / (1.0 + np.exp(-x))

    def get_weights(self) -> dict[str, dict[str, float] | float]:
        """
        Get updated weights and confidence multiplier.

        Returns:
            Dict with:
                - strategy_weights: Dict[str, float]
                - feature_weights: Dict[str, float]
                - confidence_multiplier: float
        """
        # Handle insufficient global data
        if not self.global_strategy_history or all(
            len(v) < self.min_trades for v in self.global_strategy_history.values()
        ):
            # Fallback to equal weights
            n_strats = len(self.global_strategy_history) or 1
            global_strategy_weights = (
                {k: 1.0 / n_strats for k in self.global_strategy_history.keys()}
                if self.global_strategy_history
                else {}
            )
        else:
            strategy_scores = self._compute_strategy_scores(self.global_strategy_history)
            global_strategy_weights = self._softmax(strategy_scores)

        if not self.global_feature_history or all(
            len(v) < self.min_trades for v in self.global_feature_history.values()
        ):
            n_feats = len(self.global_feature_history) or 1
            global_feature_weights = (
                {k: 1.0 / n_feats for k in self.global_feature_history.keys()}
                if self.global_feature_history
                else {}
            )
        else:
            feature_scores = self._compute_feature_scores(self.global_feature_history)
            global_feature_weights = self._softmax(feature_scores)

        # Regime-specific weights
        if (
            self.current_regime is None
            or self.current_regime not in self.regime_strategy_history
            or all(
                len(v) < self.min_trades
                for v in self.regime_strategy_history[self.current_regime].values()
            )
        ):
            regime_strategy_weights = global_strategy_weights
        else:
            regime_strategy_scores = self._compute_strategy_scores(
                self.regime_strategy_history[self.current_regime]
            )
            regime_strategy_weights = self._softmax(regime_strategy_scores)

        if (
            self.current_regime is None
            or self.current_regime not in self.regime_feature_history
            or all(
                len(v) < self.min_trades
                for v in self.regime_feature_history[self.current_regime].values()
            )
        ):
            regime_feature_weights = global_feature_weights
        else:
            regime_feature_scores = self._compute_feature_scores(
                self.regime_feature_history[self.current_regime]
            )
            regime_feature_weights = self._softmax(regime_feature_scores)

        # Blend weights: regime_prob * regime_weight + (1-regime_prob) * global_weight
        blended_strategy_weights = {}
        all_strats = set(
            list(global_strategy_weights.keys()) + list(regime_strategy_weights.keys())
        )
        for strat in all_strats:
            g = global_strategy_weights.get(strat, 0.0)
            r = regime_strategy_weights.get(strat, 0.0)
            blended = self.regime_probability * r + (1 - self.regime_probability) * g
            blended_strategy_weights[strat] = blended

        blended_feature_weights = {}
        all_feats = set(list(global_feature_weights.keys()) + list(regime_feature_weights.keys()))
        for feat in all_feats:
            g = global_feature_weights.get(feat, 0.0)
            r = regime_feature_weights.get(feat, 0.0)
            blended = self.regime_probability * r + (1 - self.regime_probability) * g
            blended_feature_weights[feat] = blended

        # Clip and normalize
        blended_strategy_weights = self._clip_and_normalize(blended_strategy_weights)
        blended_feature_weights = self._clip_and_normalize(blended_feature_weights)

        # Confidence multiplier: sigmoid(avg_sharpe) * regime_confidence
        avg_sharpe = self._average_sharpe(self.global_strategy_history)
        confidence_multiplier = self._sigmoid(avg_sharpe) * self.regime_probability

        return {
            "strategy_weights": blended_strategy_weights,
            "feature_weights": blended_feature_weights,
            "confidence_multiplier": float(confidence_multiplier),
        }
