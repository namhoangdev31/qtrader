"""Probabilistic strategy implementation that outputs confidence-scored signals."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import polars as pl

from qtrader.core.container import container
from qtrader.core.execution_guard import require_initialized
from qtrader.core.types import SignalEvent, ValidatedFeatures
from qtrader.strategy.base import BaseStrategy

_LOG = container.get("logger")


class ProbabilisticStrategy(BaseStrategy):
    """
    Strategy that generates probabilistic signals instead of threshold-based signals.

    This strategy takes in multiple alpha features and outputs signals with
    confidence scores rather than discrete BUY/SELL/HOLD decisions based on
    fixed thresholds.
    """

    def __init__(
        self,
        symbol: str,
        alpha_weights: dict[str, float] | None = None,
        model_confidence: float = 0.7,
        **kwargs,
    ) -> None:
        """
        Initialize the probabilistic strategy.

        Args:
            symbol: Primary trading symbol for this strategy
            alpha_weights: Weights for each alpha feature. If None, equal weights
            model_confidence: Base confidence level for signals (0.0 to 1.0)
            **kwargs: Additional arguments passed to BaseStrategy
        """
        super().__init__(symbol=symbol, **kwargs)
        self.alpha_weights = alpha_weights
        self.model_confidence = model_confidence

    def on_signal(self, event: SignalEvent) -> list:
        """
        Convert a probabilistic signal into orders.

        This method expects the SignalEvent to contain probability distributions
        for BUY, SELL, and HOLD outcomes rather than a discrete signal type.

        Args:
            event: SignalEvent with probability metadata

        Returns:
            List of OrderEvent objects to be submitted
        """
        buy_prob = event.metadata.get("buy_prob", 0.33)
        sell_prob = event.metadata.get("sell_prob", 0.33)
        hold_prob = event.metadata.get("hold_prob", 0.33)

        total_prob = buy_prob + sell_prob + hold_prob
        if total_prob > 0:
            buy_prob /= total_prob
            sell_prob /= total_prob
            hold_prob /= total_prob
        else:
            buy_prob = sell_prob = hold_prob = 1.0 / 3.0

        if buy_prob > sell_prob and buy_prob > hold_prob:
            signal_type = "BUY"
            probability = buy_prob
        elif sell_prob > buy_prob and sell_prob > hold_prob:
            signal_type = "SELL"
            probability = sell_prob
        else:
            signal_type = "HOLD"
            probability = hold_prob

        uniform_prob = 1.0 / 3.0
        strength = max(0.0, probability - uniform_prob) * 1.5  # Scale to [0, 1]
        strength = strength * self.model_confidence
        if signal_type == "HOLD" or strength < 0.1:
            _LOG.debug(f"Holding position for {self.symbol} (strength: {strength:.3f})")
            return []
        position_size = self.capital * strength * 0.1  # Max 10% of capital per signal
        side = "BUY" if signal_type == "BUY" else "SELL"
        order = self.create_order(quantity=position_size, side=side, order_type="MARKET")
        _LOG.info(
            f"Generated {signal_type} signal for {self.symbol} "
            f"(prob: {probability:.3f}, strength: {strength:.3f}, size: {position_size:.2f})"
        )

        return [order]

    def compute_signals(self, features: dict[str, pl.Series]) -> SignalEvent:
        """
        Compute trading signals using probabilistic approach from alpha features.

        Args:
            features: Dictionary mapping alpha names to their feature series

        Returns:
            SignalEvent with probabilistic signal and confidence scores
        """
        if not features:
            raise ValueError("Features dictionary cannot be empty")

        lengths = [series.len() for series in features.values()]
        if len(set(lengths)) != 1:
            raise ValueError(
                f"All feature series must have the same length. Got lengths: {lengths}"
            )

        for name, series in features.items():
            if series.dtype != pl.Float64:
                raise ValueError(f"Feature '{name}' must be Float64, got {series.dtype}")

        first_series = next(iter(features.values()))
        weighted_sum = pl.Series([0.0] * first_series.len(), dtype=pl.Float64).alias("weighted_sum")

        if self.alpha_weights is None:
            weight = 1.0 / len(features)
            weights = {name: weight for name in features.keys()}
        else:
            total_weight = sum(self.alpha_weights.values())
            if total_weight <= 0:
                raise ValueError("Sum of alpha_weights must be positive")
            weights = {
                name: self.alpha_weights.get(name, 0.0) / total_weight for name in features.keys()
            }

        for name, series in features.items():
            weight = weights[name]
            weighted_sum = weighted_sum + (series * weight)

        latest_value = weighted_sum[-1]

        z_score = latest_value
        signal_strength = min(1.0, max(0.0, abs(z_score) / 3.0))

        if signal_strength < 0.15:
            buy_prob = 1.0 / 3.0
            sell_prob = 1.0 / 3.0
            hold_prob = 1.0 / 3.0
        else:
            if z_score > 0:
                raw_buy = 0.5 + 0.5 * (1.0 - 1.0 / (1.0 + abs(z_score)))
                raw_sell = 1.0 - raw_buy
            else:
                raw_sell = 0.5 + 0.5 * (1.0 - 1.0 / (1.0 + abs(z_score)))
                raw_buy = 1.0 - raw_sell

            hold_base = max(0.1, 1.0 - signal_strength * 2.0)
            direction_prob = 1.0 - hold_base

            buy_prob = raw_buy * direction_prob
            sell_prob = raw_sell * direction_prob
            hold_prob = hold_base

            total = buy_prob + sell_prob + hold_prob
            buy_prob /= total
            sell_prob /= total
            hold_prob /= total

        buy_prob = buy_prob * self.model_confidence + (1.0 - self.model_confidence) * (1.0 / 3.0)
        sell_prob = sell_prob * self.model_confidence + (1.0 - self.model_confidence) * (1.0 / 3.0)
        hold_prob = hold_prob * self.model_confidence + (1.0 - self.model_confidence) * (1.0 / 3.0)

        total_prob = buy_prob + sell_prob + hold_prob
        buy_prob /= total_prob
        sell_prob /= total_prob
        hold_prob /= total_prob

        return SignalEvent(
            symbol=self.symbol,
            timestamp=datetime.utcnow(),
            signal_type="PROBABILISTIC",
            strength=Decimal(str(max(buy_prob, sell_prob, hold_prob))),
            metadata={
                "latest_value": float(latest_value),
                "z_score": float(z_score),
                "signal_strength": float(signal_strength),
                "buy_prob": float(buy_prob),
                "sell_prob": float(sell_prob),
                "hold_prob": float(hold_prob),
                "model_confidence": float(self.model_confidence),
                "alpha_weights": weights,
            },
        )

    @require_initialized
    async def generate_signal(self, validated_features: ValidatedFeatures) -> SignalEvent:
        """
        Generate a trading signal from validated features.

        This method adapts the ValidatedFeatures to the format expected by compute_signals.

        Args:
            validated_features: Validated features containing the latest feature values

        Returns:
            SignalEvent containing the trading signal
        """
        features_dict = {}
        for name, value in validated_features.features.items():
            features_dict[name] = pl.Series([value])  # length 1 series
        return self.compute_signals(features_dict)
