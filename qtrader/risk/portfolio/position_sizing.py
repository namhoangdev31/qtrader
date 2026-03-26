from __future__ import annotations


class PositionSizer:
    """
    Computes optimal position sizes using risk-management heuristics.

    Mathematical Model:
    - Kelly Criterion: f = (p(b+1) - 1) / b
    - Constraints: 0 <= f <= f_max
    """

    @staticmethod
    def compute_kelly_fraction(win_prob: float, win_loss_ratio: float, f_max: float = 1.0) -> float:
        """
        Compute the Kelly fraction for optimal positioning.

        Args:
            win_prob: Probability of a winning trade (p).
            win_loss_ratio: Average win amount / Average loss amount (b).
            f_max: Maximum allowed fraction (capping leverage).

        Returns:
            Optimal fraction f in [0, f_max].
        """
        if win_loss_ratio <= 0:
            return 0.0

        # Kelly Formula: f = (p * (b + 1) - 1) / b
        # Expected value must be positive: p * (b + 1) > 1
        raw_f = (win_prob * (win_loss_ratio + 1) - 1) / win_loss_ratio

        # Clamp between 0 and f_max
        return max(0.0, min(raw_f, f_max))
