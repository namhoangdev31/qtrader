import numpy as np
import pytest
import torch

from qtrader.hft.rl_agent import RLAgent

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

STATE_DIM = 5
ACTION_DIM = 3


def test_rl_agent_action_selection() -> None:
    """Verify that the agent can produce valid action indices."""
    agent = RLAgent(state_dim=STATE_DIM, action_dim=ACTION_DIM)
    # State: [imb, spread, vol, inventory, time]
    state = np.random.rand(STATE_DIM).astype(np.float32)

    # 1. Random action (epsilon=1.0)
    action = agent.select_action(state, epsilon=1.0)
    assert 0 <= action < ACTION_DIM

    # 2. Greedy action (epsilon=0.0)
    greedy_action = agent.select_action(state, epsilon=0.0)
    assert 0 <= greedy_action < ACTION_DIM


def test_rl_agent_reward_logic() -> None:
    """Verify the reward calculation based on slippage and risk."""
    agent = RLAgent()

    # Slippage 0.5, Penalty 0.2 -> Reward -0.7
    r = agent.compute_reward(slippage=0.5, risk_penalty=0.2)
    assert r == pytest.approx(-0.7)


def test_rl_agent_update_convergence() -> None:
    """Verify that the Q-learning update step executes without errors."""
    agent = RLAgent(state_dim=STATE_DIM, action_dim=ACTION_DIM)

    state = np.random.rand(STATE_DIM).astype(np.float32)
    next_state = np.random.rand(STATE_DIM).astype(np.float32)
    action = 1
    reward = 1.0

    # 1. Single update
    loss = agent.update(state, action, reward, next_state, done=False)
    assert isinstance(loss, float)
    assert loss >= 0.0

    # 2. Multiple updates (loss should generally fluctuate then decrease in simple cases)
    # Testing that it doesn't crash on repeated optimization
    for _ in range(5):
        agent.update(state, action, reward, next_state, done=True)


def test_rl_agent_reproducibility() -> None:
    """Ensure that torch seed control works for the internal model."""
    torch.manual_seed(42)
    agent1 = RLAgent()

    torch.manual_seed(42)
    agent2 = RLAgent()

    state = np.zeros(STATE_DIM).astype(np.float32)

    # Actions should be identical for same seed
    a1 = agent1.select_action(state, epsilon=0.0)
    a2 = agent2.select_action(state, epsilon=0.0)
    assert a1 == a2
