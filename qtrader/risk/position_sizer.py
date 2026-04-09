try:
    import qtrader_core
    from qtrader_core import SizingEngine

    sizing_engine = SizingEngine()
except ImportError as e:
    import logging

    logging.error(
        "[RISK] Institutional Risk Core (qtrader_core) is missing. System startup blocked."
    )
    raise ImportError(
        "qtrader_core is a mandatory dependency for institutional position sizing"
    ) from e


class PositionSizer(RiskModule):
    def __init__(
        self, volatility_targeting: VolatilityTargeting, max_position: float = 1.0
    ) -> None:
        self.volatility_targeting = volatility_targeting
        self.max_position = max_position

    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        signals = kwargs.get("signals")
        if signals is None:
            raise ValueError("PositionSizer requires 'signals' in kwargs")
        vol_scaling = self.volatility_targeting.compute(data)
        raw_positions = signals.cast(pl.Float64)
        scaled_positions = raw_positions * vol_scaling
        final_positions = scaled_positions.clip(-self.max_position, self.max_position)
        return final_positions.alias("position_size")
