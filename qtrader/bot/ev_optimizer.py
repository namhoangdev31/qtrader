"""Expected value and Kelly-based trade filtering."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["EVOptimizer"]


@dataclass(slots=True)
class EVOptimizer:
    """Expected value computation and trade filtering."""

    def compute_trade_ev(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        transaction_cost_bps: float,
        notional: float,
    ) -> float:
        """Expected value of a trade after transaction cost.

        EV = win_rate * avg_win - loss_rate * avg_loss - (transaction_cost_bps/10000 * notional).

        Args:
            win_rate: Probability of winning (0-1).
            avg_win: Average profit when winning.
            avg_loss: Average loss when losing (positive number).
            transaction_cost_bps: Cost in basis points per notional.
            notional: Trade notional size.

        Returns:
            Expected value in currency units.
        """
        loss_rate = 1.0 - win_rate
        ev_gross = win_rate * avg_win - loss_rate * avg_loss
        cost = (transaction_cost_bps / 10_000.0) * notional
        return ev_gross - cost

    def optimal_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        regime_confidence: float = 1.0,
        fraction: float = 0.25,
        max_f: float = 0.25,
    ) -> float:
        """Fractional Kelly with regime scaling and cap.

        f = min(kelly * fraction * regime_confidence, max_f), kelly = (wr/avg_loss) - (lr/avg_win).

        Args:
            win_rate: Probability of winning.
            avg_win: Average win size.
            avg_loss: Average loss size (positive).
            regime_confidence: Scale factor for regime (0-1).
            fraction: Fraction of full Kelly (e.g. 0.25).
            max_f: Maximum allowed fraction.

        Returns:
            Optimal fraction to risk (0 to max_f).
        """
        if not 0 <= win_rate <= 1 or avg_win <= 0 or avg_loss <= 0:
            return 0.0
        loss_rate = 1.0 - win_rate
        kelly = (win_rate / avg_loss) - (loss_rate / avg_win)
        kelly = max(0.0, kelly)
        scaled = kelly * fraction * max(0.0, regime_confidence)
        return min(scaled, max_f)

    def should_enter(
        self,
        ev: float,
        transaction_cost: float,
        min_multiple: float = 2.0,
    ) -> bool:
        """Gate: only trade if EV > min_multiple * transaction_cost.

        Args:
            ev: Expected value of the trade.
            transaction_cost: Total transaction cost in currency.
            min_multiple: Minimum EV/cost ratio to allow entry.

        Returns:
            True if entry is allowed.
        """
        if transaction_cost <= 0:
            return ev > 0
        return ev > min_multiple * transaction_cost


"""
# Pytest-style examples:
def test_ev_optimizer_should_enter() -> None:
    opt = EVOptimizer()
    assert opt.should_enter(ev=100.0, transaction_cost=40.0, min_multiple=2.0) is True
    assert opt.should_enter(ev=50.0, transaction_cost=40.0, min_multiple=2.0) is False

def test_optimal_kelly_capped() -> None:
    opt = EVOptimizer()
    f = opt.optimal_kelly(win_rate=0.6, avg_win=2.0, avg_loss=1.0, max_f=0.25)
    assert 0 <= f <= 0.25
"""
