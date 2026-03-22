"""Bayesian win-rate tracking and signal quality gating."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["WinRateOptimizer"]


@dataclass(slots=True)
class WinRateOptimizer:
    """Adaptive signal quality gating to improve win rate.

    Uses a Beta(alpha, beta) posterior for win rate; alpha_prior = target * prior_trades,
    beta_prior = (1 - target) * prior_trades. Updates with each trade outcome.
    """

    target_win_rate: float = 0.52
    prior_trades: int = 50
    _alpha: float = field(init=False)
    _beta: float = field(init=False)

    def __post_init__(self) -> None:
        self._alpha = self.target_win_rate * self.prior_trades
        self._beta = (1.0 - self.target_win_rate) * self.prior_trades

    def update(self, won: bool) -> None:
        """Bayesian update of win rate estimate after each trade.

        Args:
            won: True if the trade was profitable.
        """
        if won:
            self._alpha += 1.0
        else:
            self._beta += 1.0

    @property
    def posterior_win_rate(self) -> float:
        """E[Beta(alpha, beta)] = alpha / (alpha + beta)."""
        total = self._alpha + self._beta
        if total == 0:
            return 0.0
        return float(self._alpha / total)

    def signal_passes_filter(
        self,
        signal_strength: float,
        regime_confidence: float,
        spread_bps: float,
        avg_spread_bps: float,
        min_regime_confidence: float = 0.70,
        max_spread_multiple: float = 2.0,
    ) -> bool:
        """Returns True only if all quality gates pass.

        1. regime_confidence >= min_regime_confidence
        2. spread_bps <= max_spread_multiple * avg_spread_bps (or avg_spread_bps == 0)
        3. abs(signal_strength) >= adaptive threshold (tightens when win_rate drops)

        Args:
            signal_strength: Absolute signal magnitude.
            regime_confidence: Current regime confidence (0-1).
            spread_bps: Current spread in bps.
            avg_spread_bps: Average spread in bps.
            min_regime_confidence: Minimum required regime confidence.
            max_spread_multiple: Max allowed spread vs average.

        Returns:
            True if all gates pass.
        """
        if regime_confidence < min_regime_confidence:
            return False
        if avg_spread_bps > 0 and spread_bps > max_spread_multiple * avg_spread_bps:
            return False
        # Adaptive threshold: require stronger signal when posterior win rate is below target
        wr = self.posterior_win_rate
        threshold = 0.3 if wr >= self.target_win_rate else 0.5
        return abs(signal_strength) >= threshold

    def rr_check(
        self,
        atr: float,
        entry_price: float,
        side: str,
        min_rr: float = 1.5,
    ) -> tuple[float, float]:
        """Return (stop_loss_price, take_profit_price) enforcing min R:R.

        stop = entry ± 1*ATR, take_profit = entry ± min_rr*ATR (direction by side).

        Args:
            atr: Average True Range.
            entry_price: Entry price.
            side: "BUY" or "SELL".
            min_rr: Minimum reward:risk ratio.

        Returns:
            (stop_loss_price, take_profit_price).
        """
        if atr <= 0:
            return entry_price, entry_price
        mult = 1.0 if side.upper() == "BUY" else -1.0
        stop = entry_price - mult * atr
        take = entry_price + mult * min_rr * atr
        return (stop, take)


"""
# Pytest-style examples:
def test_posterior_win_rate() -> None:
    opt = WinRateOptimizer(target_win_rate=0.52, prior_trades=50)
    opt.update(won=True)
    opt.update(won=False)
    assert 0 <= opt.posterior_win_rate <= 1

def test_rr_check_buy() -> None:
    opt = WinRateOptimizer()
    stop, take = opt.rr_check(atr=2.0, entry_price=100.0, side="BUY", min_rr=1.5)
    assert stop < 100 < take
    assert abs(take - 100) >= 1.5 * abs(100 - stop)
"""
