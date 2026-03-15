"""qtrader.input.features — Production Feature & Factor Engineering.

Exports the key public interfaces:
  - Feature, FeaturePipeline   (protocols)
  - BaseFeature                (concrete mixin)
  - FactorEngine               (batch + streaming)
  - FeatureStore               (DuckDB + Parquet)
  - FeatureRegistry            (factor registry)
  - FactorNeutralizer          (normalizers)
  - build_default_registry     (convenience factory)
"""

from qtrader.input.features.base import BaseFeature, Feature, FeaturePipeline
from qtrader.input.features.engine import FactorEngine
from qtrader.input.features.neutralization import FactorNeutralizer
from qtrader.input.features.registry import FeatureRegistry, build_default_registry
from qtrader.input.features.store import FeatureStore

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
