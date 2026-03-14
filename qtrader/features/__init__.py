"""qtrader.features — Production Feature & Factor Engineering.

Exports the key public interfaces:
  - Feature, FeaturePipeline   (protocols)
  - BaseFeature                (concrete mixin)
  - FactorEngine               (batch + streaming)
  - FeatureStore               (DuckDB + Parquet)
  - FeatureRegistry            (factor registry)
  - FactorNeutralizer          (normalizers)
  - build_default_registry     (convenience factory)
"""

from qtrader.features.base import BaseFeature, Feature, FeaturePipeline
from qtrader.features.engine import FactorEngine
from qtrader.features.neutralization import FactorNeutralizer
from qtrader.features.registry import FeatureRegistry, build_default_registry
from qtrader.features.store import FeatureStore

__all__ = [
    "Feature",
    "FeaturePipeline",
    "BaseFeature",
    "FactorEngine",
    "FeatureStore",
    "FeatureRegistry",
    "FactorNeutralizer",
    "build_default_registry",
]
