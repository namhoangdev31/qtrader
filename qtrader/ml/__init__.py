"""Public exports for qtrader.ml."""

from qtrader.ml.autonomous import AutonomousLoop
try:
    from qtrader.ml.distributed import RayCompute, RayHyperparamTuner
    _has_ray = True
except (ImportError, ModuleNotFoundError):
    _has_ray = False
    RayCompute = None  # type: ignore
    RayHyperparamTuner = None  # type: ignore

from qtrader.ml.evaluation import ModelEvaluator, NestedCrossValidation
from qtrader.ml.feedback_loop import FeedbackController, FeedbackSample
from qtrader.ml.hmm_smoother import HMMRegimeSmoother
from qtrader.ml.online_learning import OnlineLearner, ReplayBuffer, SafeOnlineLearningEngine
from qtrader.ml.regime import RegimeDetector, VolatilityRegimeDetector
from qtrader.ml.retrain_system import RetrainDecision, RetrainSystem
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
    "FeedbackController",
    "FeedbackSample",
    "HMMRegimeSmoother",
    "ModelEvaluator",
    "ModelRotator",
    "NestedCrossValidation",
    "OnlineLearner",
    "PurgedKFoldCV",
    "RegimeDetector",
    "RegimeStabilityScore",
    "ReplayBuffer",
    "RetrainDecision",
    "RetrainSystem",
    "RotationHysteresis",
    "SafeOnlineLearningEngine",
    "VolatilityRegimeDetector",
    "WalkForwardPipeline",
]

if _has_ray:
    __all__.extend(["RayCompute", "RayHyperparamTuner"])

if _has_torch:
    __all__.append("LSTMSignalModel")

