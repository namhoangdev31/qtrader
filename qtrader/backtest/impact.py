from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["MarketImpactModel"]


@dataclass(slots=True)
class MarketImpactModel:
    """Institutional market impact models for slippage estimation."""

    @staticmethod
    def square_root_impact(  # noqa: PLR0913
        order_size: float,
        daily_vol: float,
        daily_volume: float,
        sigma_daily: float,
        y: float = 1.0,
    ) -> float:
        """Standard square-root impact model.

        Impact (bps) = y * sigma_daily * sqrt(order_size / daily_volume)
        """
        if daily_volume <= 0.0 or order_size <= 0.0:
            return 0.0
        return float(y * sigma_daily * np.sqrt(order_size / daily_volume))

    @staticmethod
    def almgren_chriss_impact(  # noqa: PLR0913
        order_size: float,
        time_horizon: float,
        daily_volume: float,
        sigma_daily: float,
        k: float = 0.1,
        gamma: float = 0.1,
    ) -> float:
        """Almgren–Chriss temporary + permanent impact (simplified).

        Args:
            order_size: Order notional in shares or contracts.
            time_horizon: Execution horizon in days.
            daily_volume: Daily traded volume.
            sigma_daily: Daily volatility (fraction).
            k: Temporary impact coefficient.
            gamma: Permanent impact coefficient.

        Returns:
            Total impact in basis points.
        """
        if daily_volume <= 0.0 or time_horizon <= 0.0 or order_size <= 0.0:
            return 0.0
        temp_impact = k * sigma_daily * (order_size / (daily_volume * time_horizon)) ** 0.5
        perm_impact = gamma * sigma_daily * (order_size / daily_volume)
        return float(temp_impact + perm_impact)

    @staticmethod
    def linear_impact(
        order_size: float,
        daily_volume: float,
        eta: float = 0.1,
    ) -> float:
        """Linear temporary impact model.

        Impact (bps) = eta * (order_size / daily_volume)
        """
        if daily_volume <= 0.0 or order_size <= 0.0:
            return 0.0
        return float(eta * (order_size / daily_volume))

    @staticmethod
    def three_fifths_impact(
        order_size: float,
        daily_volume: float,
        sigma_daily: float,
        y: float = 1.0,
    ) -> float:
        """Three-fifths power-law impact model.

        Impact (bps) = y * sigma_daily * (order_size / daily_volume) ** 0.6
        """
        if daily_volume <= 0.0 or order_size <= 0.0:
            return 0.0
        return float(y * sigma_daily * (order_size / daily_volume) ** 0.6)

    @classmethod
    def estimate_total_cost_bps(  # noqa: PLR0913
        cls,
        order_size: float,
        daily_volume: float,
        sigma_daily: float,
        commission_bps: float = 10.0,
        model: str = "square_root",
        time_horizon: float = 1.0,
    ) -> float:
        """Estimate total transaction cost in basis points.

        Args:
            order_size: Order quantity.
            daily_volume: Daily traded volume.
            sigma_daily: Daily volatility.
            commission_bps: Commission in basis points.
            model: Impact model name: ``\"square_root\"``, ``\"almgren_chriss\"``,
                or ``\"linear\"`` / ``\"three_fifths\"``.
            time_horizon: Execution horizon (days) for Almgren–Chriss.

        Returns:
            Total cost in basis points (commission + impact).
        """
        impact_bps = 0.0
        if model == "square_root":
            impact_bps = cls.square_root_impact(
                order_size=order_size,
                daily_vol=sigma_daily,
                daily_volume=daily_volume,
                sigma_daily=sigma_daily,
            )
        elif model == "almgren_chriss":
            impact_bps = cls.almgren_chriss_impact(
                order_size=order_size,
                time_horizon=time_horizon,
                daily_volume=daily_volume,
                sigma_daily=sigma_daily,
            )
        elif model == "linear":
            impact_bps = cls.linear_impact(order_size=order_size, daily_volume=daily_volume)
        elif model == "three_fifths":
            impact_bps = cls.three_fifths_impact(
                order_size=order_size,
                daily_volume=daily_volume,
                sigma_daily=sigma_daily,
            )

        return float(commission_bps + impact_bps)


if __name__ == "__main__":
    _bps = MarketImpactModel.estimate_total_cost_bps(
        order_size=10_000,
        daily_volume=1_000_000,
        sigma_daily=0.02,
        commission_bps=5.0,
        model="square_root",
    )
    assert _bps >= 5.0

