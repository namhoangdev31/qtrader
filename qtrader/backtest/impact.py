import numpy as np


class MarketImpactModel:
    """Institutional Market Impact models for slippage estimation."""
    
    @staticmethod
    def square_root_impact(  # noqa: PLR0913
        order_size: float,
        daily_vol: float,
        daily_volume: float,
        sigma_daily: float,
        y: float = 1.0,
    ) -> float:
        """
        Standard Square Root Impact Model.
        Impact (bps) = y * sigma_daily * sqrt(order_size / daily_volume)
        """
        if daily_volume <= 0:
            return 0.0
        return y * sigma_daily * np.sqrt(order_size / daily_volume)

    @staticmethod
    def almgren_chriss_impact(  # noqa: PLR0913
        order_size: float,
        time_horizon: float,
        daily_volume: float,
        sigma_daily: float,
        k: float = 0.1,
        gamma: float = 0.1,
    ) -> float:
        """
        Almgren-Chriss Temporary + Permanent Impact model.
        (Simplified version)
        """
        # Temporary impact (slippage)
        temp_impact = k * sigma_daily * (order_size / (daily_volume * time_horizon)) ** 0.5
        # Permanent impact (price shift)
        perm_impact = gamma * sigma_daily * (order_size / daily_volume)
        return temp_impact + perm_impact
