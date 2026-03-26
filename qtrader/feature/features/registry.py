"""Feature and Alpha registry for QTrader.

Provides a central registry for Feature instances so the FactorEngine
can be configured via registry lookups rather than hard-coded imports.
"""

from __future__ import annotations

import logging

import polars as pl

from qtrader.feature.features.base import Feature

__all__ = ["FeatureRegistry"]

_LOG = logging.getLogger("qtrader.feature.features.registry")

# Default registry populated with all built-in factors
_BUILT_IN: dict[str, type] = {}


class FeatureRegistry:
    """Central registry mapping feature names to Feature instances.

    Supports lazy instantiation and version tracking.
    Pattern mirrors ``qtrader.feature.alpha.registry.AlphaRegistry``.

    Example::

        registry = FeatureRegistry()
        registry.register("rsi_14", RSI(period=14))
        rsi = registry.get("rsi_14")
    """

    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}

    def register(self, name: str, feature: Feature) -> None:
        """Register a feature under a given name.

        Args:
            name: Unique key (typically ``feature.name``).
            feature: Any object satisfying the ``Feature`` protocol.
        """
        if name in self._features:
            _LOG.warning(
                "FeatureRegistry: overwriting existing feature '%s'.", name
            )
        self._features[name] = feature
        _LOG.debug("Registered feature '%s' (version=%s).", name, getattr(feature, "version", "?"))

    def get(self, name: str) -> Feature:
        """Retrieve a registered feature by name.

        Args:
            name: Feature name to look up.

        Returns:
            The registered Feature instance.

        Raises:
            KeyError: If ``name`` is not registered.
        """
        if name not in self._features:
            raise KeyError(
                f"Feature '{name}' not found in registry. "
                f"Available: {list(self._features)}"
            )
        return self._features[name]

    def list_features(self) -> list[str]:
        """Return all registered feature names.

        Returns:
            Sorted list of registered feature names.
        """
        return sorted(self._features)

    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute every registered feature and return as wide DataFrame.

        Features that fail validation or raise errors are skipped with a warning.

        Args:
            df: Input OHLCV DataFrame.

        Returns:
            Wide DataFrame with one column per feature.
        """
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
    """Build a FeatureRegistry pre-loaded with all built-in factors.

    Includes: RSI(14), ATR(14), MACD(12/26/9), BollingerBands(20),
    MomentumReturn(20), ROC(10), OBV, VWAP, DollarVolume,
    VolumeRatio(20), ForceIndex(13), LaggedReturn(1, 1),
    ReturnVolatility(20).

    Returns:
        Fully configured FeatureRegistry.
    """
    from qtrader.feature.features.factors.lagged import LaggedReturn, ReturnVolatility
    from qtrader.feature.features.factors.technical import (
        ATR,
        MACD,
        ROC,
        RSI,
        BollingerBands,
        MomentumReturn,
    )
    from qtrader.feature.features.factors.volume import (
        OBV,
        VWAP,
        DollarVolume,
        ForceIndex,
        VolumeRatio,
    )

    registry = FeatureRegistry()
    factors: list[Feature] = [
        RSI(14), ATR(14), MACD(12, 26, 9), BollingerBands(20),
        MomentumReturn(20), ROC(10),
        OBV(), VWAP(), DollarVolume(), VolumeRatio(20), ForceIndex(13),
        LaggedReturn(1, 1), ReturnVolatility(20),
    ]
    for f in factors:
        registry.register(f.name, f)
    return registry


"""
# Pytest-style unit tests:

def test_registry_get_raises_on_unknown() -> None:
    import pytest
    from qtrader.feature.features.registry import FeatureRegistry

    reg = FeatureRegistry()
    with pytest.raises(KeyError):
        reg.get("nonexistent_feature")

def test_build_default_registry_has_rsi() -> None:
    from qtrader.feature.features.registry import build_default_registry

    reg = build_default_registry()
    assert "rsi_14" in reg.list_features()

def test_registry_compute_all() -> None:
    import polars as pl
    from qtrader.feature.features.factors.technical import RSI
    from qtrader.feature.features.registry import FeatureRegistry

    reg = FeatureRegistry()
    reg.register("rsi_14", RSI(14))
    prices = [float(100 + i * 0.3) for i in range(30)]
    df = pl.DataFrame({"close": prices})
    result = reg.compute_all(df)
    assert "rsi_14" in result.columns
"""
