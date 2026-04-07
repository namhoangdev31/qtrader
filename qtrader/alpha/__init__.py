from qtrader.alpha.base import Alpha
from qtrader.alpha.microstructure import (
    AmihudIlliquidityAlpha,
    OrderImbalanceAlpha,
    VPINAlpha,
)
from qtrader.alpha.registry import AlphaEngine, AlphaRegistry
from qtrader.alpha.technical import MeanReversionAlpha, MomentumAlpha, TrendAlpha

__all__ = [
    "Alpha",
    "AlphaEngine",
    "AlphaRegistry",
    "AmihudIlliquidityAlpha",
    "MeanReversionAlpha",
    "MomentumAlpha",
    "OrderImbalanceAlpha",
    "TrendAlpha",
    "VPINAlpha",
]

# Explicitly register standard alphas after imports to ensure all classes are fully loaded.
AlphaRegistry.register(MomentumAlpha)
AlphaRegistry.register(MeanReversionAlpha)
AlphaRegistry.register(TrendAlpha)
AlphaRegistry.register(OrderImbalanceAlpha)
AlphaRegistry.register(AmihudIlliquidityAlpha)
AlphaRegistry.register(VPINAlpha)
