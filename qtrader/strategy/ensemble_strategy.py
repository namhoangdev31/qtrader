from __future__ import annotations
from decimal import Decimal
import polars as pl
from qtrader.core.events import SignalPayload
from qtrader.core.types import SignalEvent, ValidatedFeatures

try:
    from qtrader.ml.meta_learning_engine import MetaLearningEngine
except ImportError:
    MetaLearningEngine = None
from qtrader.core.container import container

_DEFAULT_META_WEIGHTS = (0.4, 0.3, 0.2, 0.1)
_DEFAULT_DECAY_PENALTY = 0.5
_DEFAULT_TEMPERATURE = 1.0
_LOG = container.get("logger")


class EnsembleStrategy:
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
        self.strategies = strategies
        self.performance_window = performance_window
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.rebalance_frequency = rebalance_frequency
        self.enable_meta_learning = enable_meta_learning
        if self.enable_meta_learning and MetaLearningEngine is not None:
            self.meta_learning_engine = MetaLearningEngine(
                window_size=meta_learning_window,
                min_trades=meta_learning_min_trades,
                temperature=_DEFAULT_TEMPERATURE,
                strategy_weights=_DEFAULT_META_WEIGHTS,
                decay_penalty=_DEFAULT_DECAY_PENALTY,
                min_weight=min_weight,
                max_weight=max_weight,
            )
        else:
            self.meta_learning_engine = None
        self._strategy_performance: dict[int, list[float]] = {i: [] for i in range(len(strategies))}
        self._strategy_weights: dict[int, float] = {
            i: 1.0 / len(strategies) for i in range(len(strategies))
        }
        self._signal_count = 0
        self._current_regime: str | None = None
        self._regime_probability: float = 0.0

    def update_regime_info(self, regime: str, regime_prob: float) -> None:
        self._current_regime = regime
        self._regime_probability = regime_prob
        if self.meta_learning_engine:
            self.meta_learning_engine.update_regime_info(regime, regime_prob)

    def compute_signals(self, features: dict[str, pl.Series]) -> SignalEvent:
        if not self.strategies:
            return SignalEvent(
                source="EnsembleStrategy",
                payload=SignalPayload(
                    symbol="UNKNOWN", signal_type="HOLD", strength=Decimal("0.0"), metadata={}
                ),
            )
        strategy_signals = {}
        for i, strategy in enumerate(self.strategies):
            try:
                signal = strategy.compute_signals(features)
                strategy_signals[i] = signal
            except Exception as e:
                _LOG.error(f"Error computing signal for strategy {i}: {e}")
                strategy_signals[i] = SignalEvent(
                    source="EnsembleStrategy",
                    payload=SignalPayload(
                        symbol="UNKNOWN", signal_type="HOLD", strength=Decimal("0.0"), metadata={}
                    ),
                )
        self._update_performance(strategy_signals)
        self._signal_count += 1
        if self._signal_count % self.rebalance_frequency == 0:
            self._rebalance_weights()
        if self.enable_meta_learning and self.meta_learning_engine:
            weights_dict = self.meta_learning_engine.get_weights()
            strategy_weights = weights_dict.get("strategy_weights")
            if not isinstance(strategy_weights, dict):
                strategy_weights = {}
            current_weights = {
                i: strategy_weights.get(self._get_strategy_name(i), 0.0)
                for i in range(len(self.strategies))
            }
            if not any(strategy_weights.values()):
                current_weights = self._strategy_weights.copy()
        else:
            current_weights = self._strategy_weights.copy()
        weight_sum = sum(current_weights.values())
        if weight_sum > 0:
            normalized_weights = {k: v / weight_sum for (k, v) in current_weights.items()}
        else:
            equal_weight = 1.0 / len(self.strategies)
            normalized_weights = {i: equal_weight for i in range(len(self.strategies))}
        combined_signal = self._combine_signals(strategy_signals, normalized_weights)
        ensemble_signal = SignalEvent(
            source="EnsembleStrategy",
            payload=SignalPayload(
                symbol="UNKNOWN",
                signal_type="ENSEMBLE",
                strength=Decimal(str(combined_signal.get("strength", 0.0))),
                metadata={
                    "buy_prob": combined_signal.get("buy_prob", 0.0),
                    "sell_prob": combined_signal.get("sell_prob", 0.0),
                    "hold_prob": combined_signal.get("hold_prob", 0.0),
                    "strategy_weights": normalized_weights,
                    "signal_components": {
                        str(i): {
                            "signal_type": sig.payload.signal_type
                            if hasattr(sig, "payload")
                            else "UNKNOWN",
                            "strength": float(sig.payload.strength)
                            if hasattr(sig, "payload")
                            else 0.0,
                            "metadata": sig.payload.metadata if hasattr(sig, "payload") else {},
                        }
                        for (i, sig) in strategy_signals.items()
                    },
                },
            ),
        )
        return ensemble_signal

    def _get_strategy_name(self, index: int) -> str:
        strategy = self.strategies[index]
        if hasattr(strategy, "__class__"):
            return strategy.__class__.__name__
        return str(strategy)

    def _update_performance(self, strategy_signals: dict) -> None:
        for i, signal in strategy_signals.items():
            if i not in self._strategy_performance:
                self._strategy_performance[i] = []
            buy_prob = signal.metadata.get("buy_prob", 0.0) if hasattr(signal, "metadata") else 0.0
            sell_prob = (
                signal.metadata.get("sell_prob", 0.0) if hasattr(signal, "metadata") else 0.0
            )
            signal_conviction = abs(buy_prob - sell_prob)
            self._strategy_performance[i].append(signal_conviction)
            if len(self._strategy_performance[i]) > self.performance_window:
                self._strategy_performance[i] = self._strategy_performance[i][
                    -self.performance_window :
                ]

    def _rebalance_weights(self) -> None:
        avg_performance = {}
        for i, performance_list in self._strategy_performance.items():
            if performance_list:
                avg_performance[i] = sum(performance_list) / len(performance_list)
            else:
                avg_performance[i] = 0.0
        if all((p <= 0 for p in avg_performance.values())):
            equal_weight = 1.0 / len(self.strategies)
            for i in range(len(self.strategies)):
                self._strategy_weights[i] = equal_weight
            return
        min_perf = min(avg_performance.values())
        shifted_perf = {i: perf - min_perf + 1e-08 for (i, perf) in avg_performance.items()}
        total_shifted = sum(shifted_perf.values())
        if total_shifted > 0:
            raw_weights = {i: perf / total_shifted for (i, perf) in shifted_perf.items()}
        else:
            equal_weight = 1.0 / len(self.strategies)
            raw_weights = {i: equal_weight for i in range(len(self.strategies))}
        constrained_weights = {}
        for i, weight in raw_weights.items():
            if weight < self.min_weight:
                constrained_weights[i] = self.min_weight
            elif weight > self.max_weight:
                constrained_weights[i] = self.max_weight
            else:
                constrained_weights[i] = weight
        weight_sum = sum(constrained_weights.values())
        if weight_sum > 0:
            for i in range(len(self.strategies)):
                self._strategy_weights[i] = constrained_weights[i] / weight_sum
        else:
            equal_weight = 1.0 / len(self.strategies)
            for i in range(len(self.strategies)):
                self._strategy_weights[i] = equal_weight
        _LOG.debug(f"Rebalanced ensemble weights: {self._strategy_weights}")

    def _combine_signals(self, strategy_signals: dict, weights: dict[int, float]) -> dict:
        buy_prob = 0.0
        sell_prob = 0.0
        hold_prob = 0.0
        for i, signal in strategy_signals.items():
            weight = weights.get(i, 0.0)
            buy_prob += weight * signal.metadata.get("buy_prob", 0.0)
            sell_prob += weight * signal.metadata.get("sell_prob", 0.0)
            hold_prob += weight * signal.metadata.get("hold_prob", 0.0)
        total_prob = buy_prob + sell_prob + hold_prob
        if total_prob > 0:
            buy_prob /= total_prob
            sell_prob /= total_prob
            hold_prob /= total_prob
        else:
            buy_prob = sell_prob = hold_prob = 1.0 / 3.0
        uniform_prob = 1.0 / 3.0
        strength = max(0.0, max(buy_prob, sell_prob, hold_prob) - uniform_prob) * 1.5
        return {
            "buy_prob": buy_prob,
            "sell_prob": sell_prob,
            "hold_prob": hold_prob,
            "strength": strength,
        }

    async def generate_signal(self, validated_features: ValidatedFeatures) -> SignalEvent:
        features_dict = {}
        for name, value in validated_features.features.items():
            features_dict[name] = pl.Series([value])
        return self.compute_signals(features_dict)
