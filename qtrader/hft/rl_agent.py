from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn, optim


class QNetwork(nn.Module):
    """
    Deep Q-Network (DQN) architecture for HFT Policy Approximation.

    Approximates the value function Q(s, a) for various execution actions
    given the current market microstructure state.
    """

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 64) -> None:
        """
        Initialize the neural network layers.

        Args:
            state_dim: Number of input features (orderbook, inventory, etc.).
            action_dim: Number of available actions (Buy/Sell/Hold).
            hidden_dim: Number of neurons in hidden layers.
        """
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass to estimate Q-values."""
        res: torch.Tensor = self.net(x)
        return res


class RLAgent:
    """
    Optimal Execution Agent using Reinforcement Learning.

    Learns to execute large orders with minimal market impact (slippage)
    and controlled inventory risk through trial and error in a simulated
    environment.
    """

    def __init__(
        self,
        state_dim: int = 5,
        action_dim: int = 3,
        gamma: float = 0.99,
        lr: float = 1e-3,
    ) -> None:
        """
        Initialize the agent with a Q-network and optimizer.

        Args:
            state_dim: Input space dimension.
            action_dim: Action space dimension (0: Buy, 1: Sell, 2: Hold).
            gamma: Discount factor for future rewards.
            lr: Learning rate for backpropagation.
        """
        self.gamma = gamma
        self.action_dim = action_dim
        self.model = QNetwork(state_dim, action_dim)
        self.optimizer = optim.Adam(self.model.parameters(), lr=lr)
        self.loss_fn = nn.MSELoss()

    def select_action(self, state: np.ndarray[Any, Any], epsilon: float = 0.1) -> int:
        """
        Choose an action based on epsilon-greedy exploration strategy.

        Args:
            state: Current environment state features.
            epsilon: Exploration probability.

        Returns:
            Selected action index.
        """
        if np.random.rand() < epsilon:
            return int(np.random.randint(0, self.action_dim))

        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            q_values = self.model(state_tensor)

        res: int = int(torch.argmax(q_values).item())
        return res

    def compute_reward(self, slippage: float, risk_penalty: float) -> float:
        """
        Calculate the step-wise reward.

        Mathematical Model:
        r = - slippage - risk_penalty

        Args:
            slippage: Realized execution slippage relative to mid-price.
            risk_penalty: Cost of holding inventory (exposure).
        """
        return -slippage - risk_penalty

    def update(
        self,
        state: np.ndarray[Any, Any],
        action: int,
        reward: float,
        next_state: np.ndarray[Any, Any],
        done: bool,
    ) -> float:
        """
        Perform a Q-learning update step.

        Logic:
        Q(s,a) = r + gamma * max Q(s', a')

        Args:
            state: Pre-action state.
            action: Action taken.
            reward: Immediate feedback received.
            next_state: Resulting state.
            done: Whether the episode finished.

        Returns:
            Computed MSE loss for tracking.
        """
        # Conversion to Tensors
        state_t = torch.FloatTensor(state).unsqueeze(0)
        next_state_t = torch.FloatTensor(next_state).unsqueeze(0)
        reward_t = torch.FloatTensor([reward])
        action_t = torch.LongTensor([action])
        done_flag = 1.0 if done else 0.0
        done_t = torch.FloatTensor([done_flag])

        # Current Q-Value prediction
        current_q = self.model(state_t).gather(1, action_t.unsqueeze(1))

        # Target Q-Value generation (Bellman equation)
        with torch.no_grad():
            max_next_q = self.model(next_state_t).max(1)[0]
            target_q = reward_t + (1 - done_t) * self.gamma * max_next_q

        # Optimization
        loss = self.loss_fn(current_q.squeeze(), target_q.squeeze())

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return float(loss.item())
