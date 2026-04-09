import numpy as np
import pytest
from qtrader.ml.online_learning import OnlineLearner, ReplayBuffer, SafeOnlineLearningEngine


@pytest.fixture
def engine() -> SafeOnlineLearningEngine:
    return SafeOnlineLearningEngine(min_performance_gain=1e-06)


@pytest.fixture
def buffer() -> ReplayBuffer:
    return ReplayBuffer(capacity=100)


@pytest.fixture
def base_model() -> OnlineLearner:
    model = OnlineLearner(eta0=0.1)
    model.update(np.array([[1.0, 2.0]]), np.array([5.0]))
    return model


def test_replay_buffer_logic(buffer: ReplayBuffer) -> None:
    for i in range(150):
        buffer.push(np.array([float(i), 0.0]), float(i))
    assert buffer.size == 100
    (x_batch, y_batch) = buffer.sample(32)
    assert x_batch.shape == (32, 2)
    assert y_batch.shape == (32,)


def test_learning_engine_candidate_generation(
    engine: SafeOnlineLearningEngine, buffer: ReplayBuffer, base_model: OnlineLearner
) -> None:
    original_weights = base_model.coefficients.copy()
    buffer.push(np.array([1.0, 2.0]), 10.0)
    candidate = engine.generate_candidate(base_model, buffer, batch_size=1)
    assert not np.array_equal(candidate.coefficients, original_weights)
    assert np.array_equal(base_model.coefficients, original_weights)


def test_learning_engine_promotion_success(
    engine: SafeOnlineLearningEngine, base_model: OnlineLearner
) -> None:
    worse_model = SafeOnlineLearningEngine().generate_candidate(base_model, ReplayBuffer())
    worse_model.weights += 10.0
    x_val = np.array([[1.0, 2.0], [2.0, 4.0]])
    y_val = base_model.predict(x_val)
    report = engine.validate_and_promote(worse_model, base_model, (x_val, y_val))
    assert report.promotion_authorized is True
    assert report.performance_gain > 0


def test_learning_engine_rejection_on_degradation(
    engine: SafeOnlineLearningEngine, base_model: OnlineLearner
) -> None:
    degraded_model = SafeOnlineLearningEngine().generate_candidate(base_model, ReplayBuffer())
    degraded_model.weights += 5.0
    x_val = np.array([[1.0, 2.0]])
    y_val = base_model.predict(x_val)
    report = engine.validate_and_promote(base_model, degraded_model, (x_val, y_val))
    assert report.promotion_authorized is False
    assert report.performance_gain < 0
