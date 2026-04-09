import math
from typing import Any
from loguru import logger


class OnlineMetaLearner:
    def __init__(
        self,
        n_memory: int = 100,
        strategy_min_weight: float = 0.01,
        strategy_max_weight: float = 0.5,
        feature_min_weight: float = 0.01,
        feature_max_weight: float = 0.5,
        ic_threshold: float = 0.02,
        temperature: float = 1.0,
    ) -> None:
        self.regime_states: dict[Any, dict[str, Any]] = {}
        self.alpha = 2.0 / (n_memory + 1)
        self.strategy_min_weight = strategy_min_weight
        self.strategy_max_weight = strategy_max_weight
        self.feature_min_weight = feature_min_weight
        self.feature_max_weight = feature_max_weight
        self.ic_threshold = ic_threshold
        self.temperature = temperature

    def _get_initial_state(self) -> dict[str, Any]:
        return {"strategy_weights": {}, "feature_weights": {}, "risk_multiplier": 1.0}

    def _compute_suggested_strategy_weights(self, feedback: dict[str, Any]) -> dict[str, float]:
        strategy_scores = feedback.get("strategy_scores", {})
        if not strategy_scores:
            return {}
        max_score = max(strategy_scores.values())
        exp_scores = {
            s: math.exp((score - max_score) / self.temperature)
            for (s, score) in strategy_scores.items()
        }
        total = sum(exp_scores.values())
        if total == 0:
            return {s: 1.0 / len(strategy_scores) for s in strategy_scores}
        return {s: exp_score / total for (s, exp_score) in exp_scores.items()}

    def _compute_suggested_feature_weights(self, feedback: dict[str, Any]) -> dict[str, float]:
        feature_scores = feedback.get("feature_scores", {})
        raw_weights = {}
        for feature, ic in feature_scores.items():
            weight = max(0.0, ic - self.ic_threshold)
            raw_weights[feature] = weight
        total = sum(raw_weights.values())
        if total > 0:
            return {f: w / total for (f, w) in raw_weights.items()}
        else:
            if feature_scores:
                uniform = 1.0 / len(feature_scores)
                return {f: uniform for f in feature_scores}
            return {}

    def _compute_suggested_risk_multiplier(self, feedback: dict[str, Any]) -> float:
        risk_feedback = feedback.get("risk_feedback", {})
        max_drawdown = risk_feedback.get("max_drawdown", 0.0)
        return 1.0 / (1.0 + max_drawdown * 10.0)

    def _update_weights(
        self,
        current_weights: dict[str, float],
        suggested_weights: dict[str, float],
        min_weight: float,
        max_weight: float,
    ) -> dict[str, float]:
        all_keys = set(current_weights.keys()) | set(suggested_weights.keys())
        new_weights = {}
        for key in all_keys:
            cw = current_weights.get(key, 0.0)
            sw = suggested_weights.get(key, 0.0)
            raw_new = (1 - self.alpha) * cw + self.alpha * sw
            change = raw_new - cw
            if cw == 0.0:
                max_change = 0.02
            else:
                max_change = 0.2 * abs(cw)
            if abs(change) > max_change:
                change = math.copysign(min(abs(change), max_change), change)
                new_weight = cw + change
            else:
                new_weight = raw_new
            new_weight = max(min_weight, min(max_weight, new_weight))
            new_weights[key] = new_weight
        total = sum(new_weights.values())
        if total > 0:
            for key in new_weights:
                new_weights[key] /= total
        elif all_keys:
            uniform = 1.0 / len(all_keys)
            for key in new_weights:
                new_weights[key] = uniform
        else:
            pass
        return new_weights

    def _update_strategy_weights(self, state: dict[str, Any], feedback: dict[str, Any]) -> None:
        suggested = self._compute_suggested_strategy_weights(feedback)
        state["strategy_weights"] = self._update_weights(
            state["strategy_weights"], suggested, self.strategy_min_weight, self.strategy_max_weight
        )

    def _update_feature_weights(self, state: dict[str, Any], feedback: dict[str, Any]) -> None:
        suggested = self._compute_suggested_feature_weights(feedback)
        state["feature_weights"] = self._update_weights(
            state["feature_weights"], suggested, self.feature_min_weight, self.feature_max_weight
        )

    def _update_risk_multiplier(self, state: dict[str, Any], feedback: dict[str, Any]) -> None:
        current = state["risk_multiplier"]
        suggested = self._compute_suggested_risk_multiplier(feedback)
        raw_new = (1 - self.alpha) * current + self.alpha * suggested
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
        new_risk = max(0.5, min(2.0, new_risk))
        state["risk_multiplier"] = new_risk

    def update(self, feedback: dict[str, Any], regime: Any) -> dict[str, Any]:
        try:
            if regime not in self.regime_states:
                self.regime_states[regime] = self._get_initial_state()
            state = self.regime_states[regime]
            self._update_strategy_weights(state, feedback)
            self._update_feature_weights(state, feedback)
            self._update_risk_multiplier(state, feedback)
            return {
                "strategy_weights": state["strategy_weights"].copy(),
                "feature_weights": state["feature_weights"].copy(),
                "risk_multiplier": state["risk_multiplier"],
            }
        except Exception as e:
            logger.info("Error in OnlineMetaLearner.update: %s", e)
            if regime in self.regime_states:
                state = self.regime_states[regime]
                return {
                    "strategy_weights": state["strategy_weights"].copy(),
                    "feature_weights": state["feature_weights"].copy(),
                    "risk_multiplier": state["risk_multiplier"],
                }
            else:
                return {"strategy_weights": {}, "feature_weights": {}, "risk_multiplier": 1.0}
