from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Dict

__all__ = ["VolTargetSizer", "ATRPositionSizer", "RiskParitySizer"]


@dataclass(slots=True)
class VolTargetSizer:
    """AQR-style volatility targeting. Scales position to hit target_vol."""

    target_vol: float = 0.10
    lookback: int = 20

    def size(self, symbol: str, realized_vol: float, capital: float) -> float:
        """Compute target dollar notional for a symbol.

        Args:
            symbol: Instrument identifier (unused, for interface completeness).
            realized_vol: Realised or estimated volatility (annualised or target-consistent).
            capital: Total capital allocated to the strategy.

        Returns:
            Target dollar position value. Returns 0.0 if volatility is non-positive.
        """
        if realized_vol <= 0.0 or capital <= 0.0:
            return 0.0
        position_value = (self.target_vol / realized_vol) * capital
        return float(position_value)


@dataclass(slots=True)
class ATRPositionSizer:
    """Size based on ATR for constant dollar risk per trade."""

    risk_per_trade_pct: float = 0.01

    def size(self, capital: float, atr: float, price: float) -> float:
        """Compute number of shares based on ATR and risk budget.

        Args:
            capital: Total trading capital.
            atr: Average True Range in price units.
            price: Current asset price.

        Returns:
            Number of shares to trade (float, already floored). Returns 0.0 for
            non-positive ATR or price.
        """
        if atr <= 0.0 or price <= 0.0 or capital <= 0.0:
            return 0.0
        dollar_risk_per_share = atr
        total_risk_budget = capital * self.risk_per_trade_pct
        raw_shares = total_risk_budget / dollar_risk_per_share
        return float(max(0, floor(raw_shares)))


@dataclass(slots=True)
class RiskParitySizer:
    """Equal risk contribution across all assets."""

    def size(self, vols: Dict[str, float], capital: float) -> Dict[str, float]:
        """Allocate capital according to inverse-volatility weights.

        Args:
            vols: Mapping of symbol to volatility (must be positive to receive allocation).
            capital: Total capital to distribute.

        Returns:
            Dictionary of symbol to dollar allocation, summing approximately to capital.
        """
        positive = {s: v for s, v in vols.items() if v > 0.0}
        if not positive or capital <= 0.0:
            return {s: 0.0 for s in vols}

        inv_vol = {s: 1.0 / v for s, v in positive.items()}
        total = sum(inv_vol.values())
        if total <= 0.0:
            n = len(positive)
            equal_alloc = capital / float(n)
            return {s: equal_alloc for s in vols}

        weights = {s: v / total for s, v in inv_vol.items()}
        allocations = {s: w * capital for s, w in weights.items()}

        return {s: allocations.get(s, 0.0) for s in vols}


"""
Pytest-style examples (conceptual):

def test_vol_target_sizer_inverse_vol() -> None:
    sizer = VolTargetSizer(target_vol=0.1)
    low_vol = sizer.size("A", realized_vol=0.1, capital=100_000.0)
    high_vol = sizer.size("A", realized_vol=0.2, capital=100_000.0)
    assert low_vol > high_vol


def test_atr_sizer_zero_for_zero_atr() -> None:
    sizer = ATRPositionSizer(risk_per_trade_pct=0.01)
    shares = sizer.size(capital=100_000.0, atr=0.0, price=100.0)
    assert shares == 0.0


def test_risk_parity_sums_to_capital() -> None:
    sizer = RiskParitySizer()
    vols = {"A": 0.1, "B": 0.2}
    allocations = sizer.size(vols, capital=100_000.0)
    assert abs(sum(allocations.values()) - 100_000.0) < 1e-6
"""

