import numpy as np
import pytest

from qtrader.ml.online_learning import OnlineLearner, ReplayBuffer, SafeOnlineLearningEngine


@pytest.fixture
def engine() -> SafeOnlineLearningEngine:
    """Initialize SafeOnlineLearningEngine with linear scaling defaults."""
    return SafeOnlineLearningEngine(min_performance_gain=1e-6)


@pytest.fixture
def buffer() -> ReplayBuffer:
    """Initialize ReplayBuffer with 100 capacity."""
    return ReplayBuffer(capacity=100)


@pytest.fixture
def base_model() -> OnlineLearner:
    """Initialize a model with 2 features."""
    model = OnlineLearner(eta0=0.1)
    # Prime with 1 sample to initialize weights
    model.update(np.array([[1.0, 2.0]]), np.array([5.0]))
    return model


def test_replay_buffer_logic(buffer: ReplayBuffer) -> None:
    """Verify that the replay buffer correctly manages samples and capacity."""
    # 1. Fill buffer
    for i in range(150):
        buffer.push(np.array([float(i), 0.0]), float(i))

    assert buffer.size == 100

    # 2. Sample batch
    x_batch, y_batch = buffer.sample(32)
    assert x_batch.shape == (32, 2)
    assert y_batch.shape == (32,)


def test_learning_engine_candidate_generation(
    engine: SafeOnlineLearningEngine, buffer: ReplayBuffer, base_model: OnlineLearner
) -> None:
    """Verify that candidate generation does not modify the production model."""
    original_weights = base_model.coefficients.copy()

    # 1. Add data to buffer
    buffer.push(np.array([1.0, 2.0]), 10.0)

    # 2. Generate candidate
    candidate = engine.generate_candidate(base_model, buffer, batch_size=1)

    # Check that candidate evolved
    assert not np.array_equal(candidate.coefficients, original_weights)
    # Check that base_model is static
    assert np.array_equal(base_model.coefficients, original_weights)


def test_learning_engine_promotion_success(
    engine: SafeOnlineLearningEngine, base_model: OnlineLearner
) -> None:
    """Verify that a model with better performance is promoted."""
    # 1. Create a "shifted" model that is intentionally worse
    worse_model = SafeOnlineLearningEngine().generate_candidate(base_model, ReplayBuffer())  # No-op
    worse_model.weights += 10.0  # Introduce massive error

    # 2. Create validation data that matches the base_model better
    x_val = np.array([[1.0, 2.0], [2.0, 4.0]])
    y_val = base_model.predict(x_val)  # Perfect fit for base_model

    # 3. Validate base_model (new) vs worse_model (old)
    # Wait, the logic is Validate(theta_new) vs Validate(theta_old)
    report = engine.validate_and_promote(worse_model, base_model, (x_val, y_val))

    assert report.promotion_authorized is True
    assert report.performance_gain > 0


def test_learning_engine_rejection_on_degradation(
    engine: SafeOnlineLearningEngine, base_model: OnlineLearner
) -> None:
    """Verify that models with worse performance are rejected."""
    # 1. Create a "candidate" that is intentionally degraded
    degraded_model = SafeOnlineLearningEngine().generate_candidate(base_model, ReplayBuffer())
    degraded_model.weights += 5.0

    # 2. Validation data
    x_val = np.array([[1.0, 2.0]])
    y_val = base_model.predict(x_val)

    # 3. Validate degraded (new) vs base (old)
    report = engine.validate_and_promote(base_model, degraded_model, (x_val, y_val))

    assert report.promotion_authorized is False
    assert report.performance_gain < 0
