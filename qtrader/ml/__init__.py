"""Public exports for qtrader.ml."""

from qtrader.ml.autonomous import AutonomousLoop
from qtrader.ml.distributed import RayCompute, RayHyperparamTuner
from qtrader.ml.evaluation import ModelEvaluator, NestedCrossValidation
from qtrader.ml.hmm_smoother import HMMRegimeSmoother
from qtrader.ml.regime import RegimeDetector, VolatilityRegimeDetector
from qtrader.ml.rotation import ModelRotator
from qtrader.ml.stability import RegimeStabilityScore, RotationHysteresis
from qtrader.ml.walk_forward import PurgedKFoldCV, WalkForwardPipeline

# Try to import pytorch models, but don't fail if torch is not available or broken
try:
    from qtrader.ml.pytorch_models import LSTMSignalModel

    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False
    LSTMSignalModel = None  # type: ignore

__all__ = [
    "AutonomousLoop",
    "RayCompute",
    "RayHyperparamTuner",
    "ModelEvaluator",
    "NestedCrossValidation",
    "HMMRegimeSmoother",
    "RegimeDetector",
    "VolatilityRegimeDetector",
    "ModelRotator",
    "RegimeStabilityScore",
    "RotationHysteresis",
    "PurgedKFoldCV",
    "WalkForwardPipeline",
]

if _has_torch:
    __all__.append("LSTMSignalModel")

