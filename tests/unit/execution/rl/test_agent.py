from unittest.mock import MagicMock

import pytest
import torch

from qtrader.execution.rl.agent import RLOrderExecutionAgent


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with RL hyperparameters."""
    cfg = MagicMock()
    # RL Agent Configuration
    cfg.rl = {"agent": {"learning_rate": 0.01, "gamma": 0.99}}
    return cfg


def test_rl_agent_inference_stability(execution_config: MagicMock) -> None:
    """Verify that same state input yields consistent action distributions in deterministic mode."""
    state_dim = 10
    agent = RLOrderExecutionAgent(execution_config, state_dim)

    state = [0.1] * state_dim

    # 2 consecutive deterministic calls should yield the same action
    a1 = agent.act(state, deterministic=True)
    a2 = agent.act(state, deterministic=True)

    assert a1 == a2  # noqa: S101
    assert a1 in [-2, -1, 0, 1, 2]  # noqa: S101


def test_rl_agent_learning_convergence(execution_config: MagicMock) -> None:
    """Verify that the policy probability for rewarded actions increases over time."""
    state_dim = 4
    agent = RLOrderExecutionAgent(execution_config, state_dim)

    state = [0.5, -0.2, 0.1, 0.9]

    # Baseline probability for action 0 (index 2) before update
    with torch.no_grad():
        probs_before = agent._policy(torch.FloatTensor(state).unsqueeze(0))
        p_before = probs_before[0, 2].item()

    # Simulate 50 episodes where choosing target_action yields high reward
    for _ in range(50):
        # Forward pass MUST be inside loop to attach gradients for each update
        probs = agent._policy(torch.FloatTensor(state).unsqueeze(0))
        m = torch.distributions.Categorical(probs)
        # Forced pick target action index 2 (action 0)
        agent._saved_log_probs.append(m.log_prob(torch.tensor(2)))  # type: ignore
        agent.record_reward(10.0)
        agent.update()

    # Probability after update
    with torch.no_grad():
        probs_after = agent._policy(torch.FloatTensor(state).unsqueeze(0))
        p_after = probs_after[0, 2].item()

    # Probability should have significantly increased
    assert p_after > p_before  # noqa: S101


def test_rl_agent_exploration_sampling(execution_config: MagicMock) -> None:
    """Verify that stochastic sampling populates the trajectory buffer for updates."""
    state_dim = 8
    agent = RLOrderExecutionAgent(execution_config, state_dim)

    state = [0.0] * state_dim

    # Act stochastically
    agent.act(state, deterministic=False)

    # Buffer should be filled
    assert len(agent._saved_log_probs) == 1  # noqa: S101

    # Update should clear buffer
    agent.record_reward(1.0)
    agent.update()

    assert len(agent._saved_log_probs) == 0  # noqa: S101
    assert len(agent._rewards) == 0  # noqa: S101


def test_rl_agent_empty_update_failsafe(execution_config: MagicMock) -> None:
    """Verify that update() handles empty buffers gracefully."""
    agent = RLOrderExecutionAgent(execution_config, 5)
    loss = agent.update()
    assert loss == 0.0  # noqa: S101
