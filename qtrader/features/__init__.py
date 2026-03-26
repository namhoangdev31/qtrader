"""qtrader.feature.features — Production Feature & Factor Engineering.

Exports the key public interfaces:
  - Feature, FeaturePipeline   (protocols)
  - BaseFeature                (concrete mixin)
  - FactorEngine               (batch + streaming)
  - FeatureStore               (DuckDB + Parquet)
  - FeatureRegistry            (factor registry)
  - FactorNeutralizer          (normalizers)
  - build_default_registry     (convenience factory)
"""

from qtrader.feature.features.base import BaseFeature, Feature, FeaturePipeline
from qtrader.feature.features.engine import FactorEngine
from qtrader.feature.features.neutralization import FactorNeutralizer
from qtrader.feature.features.registry import FeatureRegistry, build_default_registry
from qtrader.feature.features.store import FeatureStore

__all__ = [
    "BaseFeature",
    "FactorEngine",
    "FactorNeutralizer",
    "Feature",
    "FeaturePipeline",
    "FeatureRegistry",
    "FeatureStore",
    "build_default_registry",
]
