from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from qtrader.features.base import Feature
from qtrader.features.factors.lagged import LaggedReturn, ReturnVolatility
from qtrader.features.factors.microstructure import OrderImbalanceFactor
from qtrader.features.factors.technical import ATR, MACD, ROC, RSI, BollingerBands, MomentumReturn
from qtrader.features.factors.volume import OBV, VWAP, DollarVolume, ForceIndex, VolumeRatio

__all__ = ["FeatureRegistry"]
_LOG = logging.getLogger("qtrader.features.registry")
_BUILT_IN: dict[str, type] = {}

class FeatureRegistry:
    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}

    def register(self, name: str, feature: Feature) -> None:
        if name in self._features:
            _LOG.warning("FeatureRegistry: overwriting existing feature '%s'.", name)
        self._features[name] = feature
        _LOG.debug("Registered feature '%s' (version=%s).", name, getattr(feature, "version", "?"))

    def get(self, name: str) -> Feature:
        if name not in self._features:
            raise KeyError(
                f"Feature '{name}' not found in registry. Available: {list(self._features)}"
            )
        return self._features[name]

    def list_features(self) -> list[str]:
        return sorted(self._features)

    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for name, feature in self._features.items():
            try:
                if hasattr(feature, "validate_inputs"):
                    feature.validate_inputs(df)
                out = feature.compute(df)
                if isinstance(out, pl.Series):
                    frames.append(out.to_frame())
                elif isinstance(out, pl.DataFrame):
                    frames.append(out)
            except Exception as exc:
                _LOG.warning("FeatureRegistry.compute_all: feature '%s' error: %s", name, exc)
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="horizontal")

def build_default_registry() -> FeatureRegistry:

    registry = FeatureRegistry()
    factors: list[Feature] = [
        RSI(14),
        ATR(14),
        MACD(12, 26, 9),
        BollingerBands(20),
        MomentumReturn(20),
        ROC(10),
        OBV(),
        VWAP(),
        DollarVolume(),
        VolumeRatio(20),
        ForceIndex(13),
        LaggedReturn(1, 1),
        ReturnVolatility(20),
        OrderImbalanceFactor(5),
    ]
    for f in factors:
        registry.register(f.name, f)
    return registry
