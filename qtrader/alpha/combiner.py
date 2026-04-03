"""Consolidated Alpha Combiner: Single source of truth for factor/signal aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class AlphaBase(Protocol):
    """Protocol for alpha factors/generators."""

    name: str

    def compute(self, data: pl.DataFrame) -> pl.Series: ...
    async def generate(self, data: any) -> any: ...


@dataclass(slots=True)
class AlphaCombiner:
    """
    Combines multiple alpha factors/streams into a composite signal or feature set.
    Supports IC-weighting, equal-weighting and turnover dampening.
    """

    method: str = "ic_weighted"
    dampening_factor: float = 0.3
    _alphas: dict[str, dict[str, float]] = field(default_factory=dict, init=False)
    _previous_signal: float = 0.0

    def combine_features(
        self, market_data: pl.DataFrame, factors: list[AlphaBase]
    ) -> dict[str, pl.Series] | None:
        """Vectorized combination of multiple polars factors into a feature dict."""
        features = {}
        for alpha in factors:
            try:
                feature_series = alpha.compute(market_data)
                if feature_series.len() != len(market_data):
                    continue
                features[alpha.name] = feature_series
            except Exception as e:
                import logging

                logging.getLogger(f"qtrader.alpha.combiner").error(
                    f"Alpha {alpha.name} failed during combination: {e}"
                )
                continue  # Skip this alpha, don't fail the whole combination
        return features

    def register_signal(self, name: str, signal: float, ic: float = 1.0) -> None:
        """Register a scalar signal from a specific alpha stream."""
        self._alphas[name] = {"signal": float(signal), "ic": float(ic)}

    def get_composite_signal(self) -> float:
        """
        Compute weighted composite signal with turnover dampening.
        Returns blended signal in [-1, 1].
        """
        if not self._alphas:
            return 0.0

        ics = {k: v["ic"] for k, v in self._alphas.items()}
        weights = self._compute_weights(ics)

        new_signal = 0.0
        for name, w in weights.items():
            new_signal += w * self._alphas[name]["signal"]

        # Clamp and Dampen
        new_signal = max(-1.0, min(1.0, new_signal))
        blended = (
            1.0 - self.dampening_factor
        ) * new_signal + self.dampening_factor * self._previous_signal

        self._previous_signal = float(blended)
        return self._previous_signal

    def _compute_weights(self, ics: dict[str, float]) -> dict[str, float]:
        """Compute relative weights based on IC or Equal weighting."""
        names = list(ics.keys())
        n = len(names)
        if n == 0:
            return {}

        if self.method == "equal":
            return {name: 1.0 / n for name in names}

        # Weight by positive IC
        pos_ics = {name: max(ic, 0.0) for name, ic in ics.items()}
        total = sum(pos_ics.values())

        if total <= 0.0:
            return {name: 1.0 / n for name in names}

        return {name: val / total for name, val in pos_ics.items()}

    def update_historical_ic(
        self, alpha_name: str, predicted: pl.Series, realized: pl.Series
    ) -> float:
        """Update the IC estimate for a factor using Rank Correlation."""
        if predicted.len() < 2:
            return 0.0

        pred_rank = predicted.rank()
        real_rank = realized.rank()

        ic_val = float(
            pl.DataFrame({"p": pred_rank, "r": real_rank}).select(pl.corr("p", "r")).item() or 0.0
        )

        if alpha_name in self._alphas:
            self._alphas[alpha_name]["ic"] = ic_val
        return ic_val
