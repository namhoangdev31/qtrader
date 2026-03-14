from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

__all__ = ["AlphaCombiner"]


@dataclass(slots=True)
class AlphaCombiner:
    """Combine multiple alpha streams into a composite signal."""

    method: str = "ic_weighted"
    _alphas: dict[str, dict[str, float]] = field(default_factory=dict, init=False)
    previous_signal: float = 0.0

    def register_alpha(self, name: str, signal: float, ic: float) -> None:
        """Register or update a single alpha's signal and IC estimate.

        Args:
            name: Alpha identifier.
            signal: Current scalar signal in [-1, 1].
            ic: Rolling information coefficient estimate.
        """
        self._alphas[name] = {"signal": float(signal), "ic": float(ic)}

    def combine(self) -> float:
        """Combine all registered alphas into a single composite signal.

        Returns:
            Blended composite signal in [-1, 1], with turnover dampening.
        """
        if not self._alphas:
            return 0.0

        signals = {k: v["signal"] for k, v in self._alphas.items()}
        ics = {k: v["ic"] for k, v in self._alphas.items()}

        weights = self._compute_weights(ics)

        new_signal = 0.0
        for name, w in weights.items():
            new_signal += w * signals.get(name, 0.0)

        if new_signal > 1.0:
            new_signal = 1.0
        if new_signal < -1.0:
            new_signal = -1.0

        blended = 0.7 * new_signal + 0.3 * self.previous_signal
        if blended > 1.0:
            blended = 1.0
        if blended < -1.0:
            blended = -1.0

        self.previous_signal = blended
        return float(blended)

    def _compute_weights(self, ics: dict[str, float]) -> dict[str, float]:
        """Compute alpha weights according to the configured method."""
        names = list(ics.keys())
        n = len(names)
        if n == 0:
            return {}

        if self.method == "equal":
            w = 1.0 / float(n)
            return {name: w for name in names}

        positives = {name: max(ics[name], 0.0) for name in names}
        if self.method in ("sharpe_weighted", "ic_weighted"):
            total = sum(positives.values())
            if total <= 0.0:
                w = 1.0 / float(n)
                return {name: w for name in names}
            return {name: val / total for name, val in positives.items()}

        w = 1.0 / float(n)
        return {name: w for name in names}

    def update_ic(self, alpha_name: str, predicted: pl.Series, realized: pl.Series) -> None:
        """Update IC estimate for a given alpha using rank correlation.

        Args:
            alpha_name: Name of the alpha to update.
            predicted: Series of predicted returns.
            realized: Series of realized returns.
        """
        if predicted.len() == 0 or realized.len() == 0:
            return
        min_len = min(predicted.len(), realized.len())
        pred = predicted.head(min_len).rank()
        real = realized.head(min_len).rank()
        corr_df = pl.DataFrame({"pred": pred, "real": real})
        ic_val = float(corr_df.select(pl.corr("pred", "real")).item())
        existing = self._alphas.get(alpha_name, {"signal": 0.0, "ic": 0.0})
        existing["ic"] = ic_val
        self._alphas[alpha_name] = existing


"""
Pytest-style examples (conceptual):

def test_ic_weighted_combination() -> None:
    comb = AlphaCombiner(method="ic_weighted")
    comb.register_alpha("a1", signal=0.5, ic=0.1)
    comb.register_alpha("a2", signal=-0.5, ic=0.0)
    val = comb.combine()
    assert -1.0 <= val <= 1.0


def test_turnover_dampening() -> None:
    comb = AlphaCombiner(method="equal")
    comb.register_alpha("a1", signal=1.0, ic=0.2)
    s1 = comb.combine()
    comb.register_alpha("a1", signal=-1.0, ic=0.2)
    s2 = comb.combine()
    assert abs(s2) < 1.0
"""

