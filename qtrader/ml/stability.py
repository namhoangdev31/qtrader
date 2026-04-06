from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
import polars as pl

__all__ = ["RegimeStabilityScore", "RotationHysteresis"]

log = logging.getLogger(__name__)


@dataclass(slots=True)
class RotationHysteresis:
    """Prevent rapid regime oscillation via persistence and cooldown.

    Args:
        persistence_bars: Number of consecutive bars required to confirm a shift.
        cooldown_sec: Minimum seconds between confirmed rotations.
    """

    persistence_bars: int = 5
    cooldown_sec: int = 1800
    pending_regime: int | None = field(init=False, default=None)
    pending_count: int = field(init=False, default=0)
    last_rotation_time: float = field(init=False, default=0.0)
    current_regime: int | None = field(init=False, default=None)

    def validate_shift(self, new_regime: int) -> bool:
        """Return True if the regime shift meets stability criteria.

        Args:
            new_regime: Proposed new regime ID.

        Returns:
            True if the shift is confirmed, False otherwise.
        """
        now = time.time()

        # Cooldown check.
        if now - self.last_rotation_time < self.cooldown_sec:
            return False

        # Persistence check.
        if new_regime == self.current_regime:
            self.pending_regime = None
            self.pending_count = 0
            return False

        if new_regime == self.pending_regime:
            self.pending_count += 1
        else:
            self.pending_regime = new_regime
            self.pending_count = 1

        if self.pending_count >= self.persistence_bars:
            log.info("STABILITY | Regime shift confirmed after %s bars.", self.pending_count)
            self.current_regime = new_regime
            self.last_rotation_time = now
            return True

        return False


@dataclass(slots=True)
class RegimeStabilityScore:
    """Compute stability scores for regime sequences.

    Two complementary views:
      * Entropy of average posterior probabilities (0=unstable, 1=stable).
      * Label-change frequency over a window.
    """

    def stability_score_from_probs(
        self,
        regime_probs: pl.DataFrame,
        window: int = 20,
    ) -> float:
        """Compute a stability score from regime posterior probabilities.

        Args:
            regime_probs: DataFrame with columns ``regime_0_prob``, ``regime_1_prob``, ...
            window: Lookback window size.

        Returns:
            Stability score in [0, 1], where 1 is highly stable.
        """
        if regime_probs.height == 0:
            return 0.0
        if window <= 0:
            raise ValueError("window must be positive.")

        cols = [c for c in regime_probs.columns if c.endswith("_prob")]
        if not cols:
            raise ValueError("regime_probs must contain *_prob columns.")

        tail = regime_probs.tail(window) if regime_probs.height > window else regime_probs
        probs = tail.select(cols).to_numpy()
        mean_probs = probs.mean(axis=0)
        mean_probs = mean_probs / (mean_probs.sum() + 1e-12)

        entropy = -float(np.sum(mean_probs * np.log(mean_probs + 1e-12)))
        max_entropy = float(np.log(len(mean_probs)))
        if max_entropy == 0.0:
            return 1.0
        normalized = entropy / max_entropy
        return float(1.0 - normalized)

    def stability_score_from_labels(self, regimes: pl.Series, window: int = 20) -> float:
        """Score stability based on label-change frequency.

        Args:
            regimes: Series of integer regime labels.
            window: Lookback window for changes.

        Returns:
            Score in [0, 1]; 1 when no change in the window, 0 when changing every bar.
        """
        if regimes.len() == 0:
            return 0.0
        if window <= 1:
            raise ValueError("window must be greater than 1.")

        tail = regimes.tail(window)
        labels = tail.to_numpy()
        changes = np.sum(labels[1:] != labels[:-1])
        max_changes = labels.shape[0] - 1
        if max_changes == 0:
            return 1.0
        return float(1.0 - changes / max_changes)


if __name__ == "__main__":
    _h = RotationHysteresis(persistence_bars=2, cooldown_sec=0)
    # First shift attempt should not confirm (persistence check)
    if _h.validate_shift(1):
        raise ValueError("Hysteresis failed: shift confirmed too early")
    # Second shift attempt should confirm
    if not _h.validate_shift(1):
        raise ValueError("Hysteresis failed: shift not confirmed after persistence")

    _probs = pl.DataFrame({"regime_0_prob": [0.9, 0.9], "regime_1_prob": [0.1, 0.1]})
    _score = RegimeStabilityScore().stability_score_from_probs(_probs, window=2)
    if not (0.0 <= _score <= 1.0):
        raise ValueError(f"Stability score out of bounds: {_score}")
