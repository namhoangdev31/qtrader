from __future__ import annotations

import polars as pl

from qtrader.risk.base import RiskModule
from qtrader.risk.volatility import VolatilityTargeting


class PositionSizer(RiskModule):
    """
    Position sizing risk module.

    Converts trading signals into position sizes using volatility targeting.
    Takes in signals and market data, outputs continuous position sizes.
    """

    def __init__(
        self,
        volatility_targeting: VolatilityTargeting,
        max_position: float = 1.0,
    ) -> None:
        """
        Initialize the PositionSizer.

        Args:
            volatility_targeting: VolatilityTargeting instance for vol scaling
            max_position: Maximum absolute position size (long or short)
        """
        self.volatility_targeting = volatility_targeting
        self.max_position = max_position

    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        """
        Compute position sizes from signals and market data.

        Args:
            data: Market data DataFrame (must contain 'close' column for vol calc)
            **kwargs: Expected to contain 'signals' key with signal series
                     (values: BUY=1, SELL=-1, HOLD=0)

        Returns:
            Position size series (continuous, -max_position to +max_position)
        """
        # Extract signals from kwargs
        signals = kwargs.get('signals')
        if signals is None:
            raise ValueError("PositionSizer requires 'signals' in kwargs")

        # Get volatility scaling factor
        vol_scaling = self.volatility_targeting.compute(data)

        # Ensure signals are numeric (assuming they are already 1, -1, 0)
        # If signals contain strings, we would need to map them, but we expect numeric
        raw_positions = signals.cast(pl.Float64)

        # Apply volatility scaling
        scaled_positions = raw_positions * vol_scaling

        # Clip positions to max limits using Series.clip (vectorized)
        final_positions = scaled_positions.clip(-self.max_position, self.max_position)

        # Ensure proper naming
        final_positions = final_positions.alias("position_size")

        return final_positions