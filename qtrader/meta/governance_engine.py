from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import polars as pl

_LOG = logging.getLogger("qtrader.meta.governance_engine")


@dataclass(slots=True)
class StrategyCandidate:
    """Industrial container for automated strategy discovery outputs."""

    strategy_id: str
    expression: str
    returns: pl.Series  # Historical return series for correlation checks
    sharpe_estimate: float


class MetaGovernanceEngine:
    """
    Industrial Strategy Curation Engine.

    Prevents strategy explosion and overfitting loops by enforcing strict daily
    quotas, quality pre-filters (Sharpe estimation), and diversity (correlation) masks.
    """

    def __init__(
        self,
        max_daily_quota: int = 10,
        min_sharpe_threshold: float = 1.0,
        max_correlation_threshold: float = 0.70,
    ) -> None:
        """
        Initialize the governing parameters for research curation.

        Args:
            max_daily_quota: Absolute limit on accepted strategies per day.
            min_sharpe_threshold: Minimum expected Sharpe ratio for inclusion.
            max_correlation_threshold: Maximum allowable correlation |rho| with existing set.
        """
        self._max_daily_quota = max_daily_quota
        self._min_sharpe_threshold = min_sharpe_threshold
        self._max_correlation_threshold = max_correlation_threshold

        # Telemetry for Compliance and Audit
        self.stats = {
            "strategies_generated": 0,
            "strategies_accepted": 0,
            "mean_diversity_score": 0.0,
        }

    def curate(self, pool: list[StrategyCandidate]) -> list[StrategyCandidate]:
        """
        Rank, filter, and curate the discovery pool into an executable set.

        Args:
            pool: List of discovered strategy candidates with metadata and returns.

        Returns:
            A prioritized, non-redundant set of high-alpha strategies.
        """
        self.stats["strategies_generated"] += len(pool)

        # 1. Quality Pre-filter: Prune weak signals immediately
        high_quality = [s for s in pool if s.sharpe_estimate >= self._min_sharpe_threshold]

        # 2. Ranking: Prioritize by expected risk-adjusted performance
        ranked = sorted(high_quality, key=lambda x: x.sharpe_estimate, reverse=True)

        # 3. Diversity Filtering: Sequential Greedy selection against correlation mask
        curated: list[StrategyCandidate] = []
        for candidate in ranked:
            if len(curated) >= self._max_daily_quota:
                break

            if not self._is_highly_correlated(candidate, curated):
                curated.append(candidate)
            else:
                _LOG.debug(f"Rejecting {candidate.strategy_id} due to low diversity.")

        self.stats["strategies_accepted"] += len(curated)
        self._update_diversity_telemetry(curated)

        _LOG.info(f"[CURATION] Accepted {len(curated)}/{len(pool)} strategies.")
        return curated

    def _is_highly_correlated(
        self, candidate: StrategyCandidate, existing_set: list[StrategyCandidate]
    ) -> bool:
        """
        Check if the candidate overlaps significantly with already selected signals.

        Redundancy is calculated as the maximum absolute correlation |rho| between
        the candidate's returns and the existing set.
        """
        if not existing_set:
            return False

        for s in existing_set:
            # Fast vectorized correlation using Polars DataFrame context
            corr_val = (
                pl.DataFrame({"a": candidate.returns, "b": s.returns})
                .select(pl.corr("a", "b"))
                .item()
            )
            # Handle NaN from zero volatility
            corr = float(corr_val) if corr_val is not None else 0.0
            if abs(corr) > self._max_correlation_threshold:
                return True

        return False

    def _update_diversity_telemetry(self, curated: list[StrategyCandidate]) -> None:
        """Compute and update the mean pairwise correlation of the curated set."""
        if len(curated) < 2:  # noqa: PLR2004
            self.stats["mean_diversity_score"] = 0.0
            return

        corrs: list[float] = []
        for i in range(len(curated)):
            for j in range(i + 1, len(curated)):
                c_val = (
                    pl.DataFrame({"a": curated[i].returns, "b": curated[j].returns})
                    .select(pl.corr("a", "b"))
                    .item()
                )
                c = float(c_val) if c_val is not None else 0.0
                corrs.append(abs(c))

        if corrs:
            self.stats["mean_diversity_score"] = sum(corrs) / len(corrs)

    def get_governance_report(self) -> dict[str, Any]:
        """
        Generate a report on the effectiveness of the curation process.

        Returns:
            Telemetry dict containing acceptance rates and diversity metrics.
        """
        total = self.stats["strategies_generated"]
        accepted = self.stats["strategies_accepted"]

        return {
            "status": "CURATED",
            "accepted": accepted,
            "rejected": total - accepted,
            "mean_diversity_score": self.stats["mean_diversity_score"],
        }
