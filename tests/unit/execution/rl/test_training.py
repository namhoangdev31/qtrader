from unittest.mock import MagicMock

from qtrader.execution.rl.replay_buffer import ExperienceReplayBuffer
from qtrader.execution.rl.training import RLTrainingPipeline


def test_replay_buffer_capacity_fifo() -> None:
    """Verify FIFO eviction when buffer capacity is reached."""
    capacity = 10
    buffer = ExperienceReplayBuffer(capacity=capacity)

    # Add 15 transitions
    for i in range(15):
        buffer.add([float(i)], i, float(i), [float(i + 1)], False)

    expected_len = 10
    assert len(buffer) == expected_len

    # Oldest (0-4) should be evicted. First transition should be index 5.
    sample = buffer.sample(batch_size=10)
    # Sampling is random, but we can check if 0-4 are absent if we sample all
    all_states = [s[0][0] for s in sample]
    assert 0.0 not in all_states
    assert 14.0 in all_states


def test_training_pipeline_episode_trajectory() -> None:
    """Verify that a full episode generates expected transitions and agent update."""
    agent = MagicMock()
    # Mock act to return index 2 (action 0)
    agent.act.return_value = 0
    agent.update.return_value = 0.01

    buffer = ExperienceReplayBuffer(capacity=100)
    pipeline = RLTrainingPipeline(agent, buffer)

    # 3 steps (2 transitions)
    episode_data = [
        {"state": [0.1], "reward": 1.0},
        {"state": [0.2], "reward": 2.0},
        {"state": [0.3], "reward": 3.0},
    ]

    total_reward = pipeline.run_episode(episode_data)

    # total_reward = 1.0 + 2.0 = 3.0 (from first two steps)
    expected_reward = 3.0
    expected_buffer_len = 2
    assert total_reward == expected_reward
    assert len(buffer) == expected_buffer_len

    # Verify agent was updated once
    assert agent.update.call_count == 1
    assert agent.record_reward.call_count == 2


def test_training_pipeline_convergence_tracking() -> None:
    """Verify that train() correctly tracks rewards over epochs."""
    agent = MagicMock()
    agent.act.return_value = 0
    agent.update.return_value = 0.001

    buffer = ExperienceReplayBuffer(capacity=500)
    pipeline = RLTrainingPipeline(agent, buffer)

    # 1 episode per epoch, 2 steps each
    episode = [{"state": [0.0], "reward": 10.0}, {"state": [1.0], "reward": 0.0}]
    dataset = [episode]

    num_epochs = 5
    history = pipeline.train(dataset, n_epochs=num_epochs)

    assert len(history) == num_epochs
    assert all(h == 10.0 for h in history)
    assert agent.update.call_count == num_epochs


def test_training_pipeline_empty_failsafe() -> None:
    """Verify behavior with empty dataset or malformed episodes."""
    pipeline = RLTrainingPipeline(MagicMock(), MagicMock())

    assert pipeline.train([], n_epochs=5) == []
    assert pipeline.run_episode([]) == 0.0
    assert pipeline.run_episode([{"state": [0.1]}]) == 0.0
