from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import torch
import torch.nn.functional as F  # noqa: N812
from torch import Tensor, nn, optim

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig


_LOG = logging.getLogger("qtrader.execution.rl.agent")


class PolicyNetwork(nn.Module):
    """
    Multi-Layer Perceptron (MLP) for discrete execution policy.

    Architecture: 64-32 unit ReLU-activated hidden layers. Enforces a non-linear
    mapping between microstructure state and execution action probabilities.
    """

    def __init__(self, input_dim: int, output_dim: int) -> None:
        super().__init__()
        # Standard MLP backbone for low-latency inference (<1ms)
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, output_dim)

    def forward(self, x: Tensor) -> Tensor:
        """
        Compute action logit distribution given state tensor.
        """
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        # Softmax ensures sum(a_i) = 1.0 for valid probability exploration.
        return F.softmax(self.fc3(x), dim=-1)


class RLOrderExecutionAgent:
    """
    Reinforcement Learning Agent for microstructure order execution.

    Algorithm: REINFORCE (Monte Carlo Policy Gradient)
    Action Space: Discrete Price Offsets relative to Mid Price.
    Learning: Continuous online policy updates from Episode trajectories.

    Actions:
    [-2, -1,  0,  1,  2] ticks from mid.
    Positive -> Aggressive (buy above mid/sell below)
    Negative -> Passive (buy below mid/sell above)
    """

    def __init__(self, config: ExecutionConfig, state_dim: int) -> None:
        """
        Initialize the RL Agent with a configured policy network and optimizer.

        Args:
            config: Execution configuration containing RL hyperparameters.
            state_dim: Dimension of normalized input feature vector.
        """
        self._config = config
        self._state_dim = state_dim

        # Action-space definition (Discrete offsets from reference)
        self._actions = [-2, -1, 0, 1, 2]
        self._n_actions = len(self._actions)

        # RL Hyperparameters (Defaults optimized for zero-latency execution)
        rl_cfg = getattr(config, "rl", {}).get("agent", {})
        self._lr = float(rl_cfg.get("learning_rate", 1e-4))
        self._gamma = float(rl_cfg.get("gamma", 0.99))

        # Core Policy Model
        self._policy = PolicyNetwork(state_dim, self._n_actions)
        self._optimizer = optim.Adam(self._policy.parameters(), lr=self._lr)

        # Episode Buffer (Stateless update per episode)
        self._saved_log_probs: list[Tensor] = []
        self._rewards: list[float] = []

    def act(self, state: list[float], deterministic: bool = False) -> int:
        """
        Determine the execution action given the current market state.

        Args:
            state: Normalized microstructure feature vector.
            deterministic: If True, select highest probability (Exploitation/Production).

        Returns:
            The tick offset value (e.g. 0 for Mid).
        """
        # Convert state vector to PyTorch float tensor
        tensor_state = torch.FloatTensor(state).unsqueeze(0)

        # Forward pass through Policy Network
        probs = self._policy(tensor_state)

        if deterministic:
            # Greedy selection for production evaluation
            action_idx = int(torch.argmax(probs).item())
        else:
            # Stochastic sampling for exploration
            m = torch.distributions.Categorical(probs)
            sampled_action = m.sample()  # type: ignore[no-untyped-call]
            # Buffer the log-probability for policy gradient update
            self._saved_log_probs.append(m.log_prob(sampled_action))  # type: ignore[no-untyped-call]
            action_idx = int(sampled_action.item())

        return self._actions[action_idx]

    def record_reward(self, reward: float) -> None:
        """
        Append a scalar reward to the current episode buffer.
        """
        self._rewards.append(reward)

    def update(self) -> float:
        """
        Execute gradient descent to update policy parameters using the REINFORCE algorithm.

        Returns:
            Calculated scalar loss for telemetry.
        """
        if not self._saved_log_probs or not self._rewards:
            # Avoid updates on empty trajectories
            return 0.0

        # Loss and Return computation
        running_returns = 0.0
        policy_loss: list[Tensor] = []
        discounted_returns: list[float] = []

        # 1. Backpropagate the discounted rewards
        for reward in reversed(self._rewards):
            running_returns = reward + self._gamma * running_returns
            discounted_returns.insert(0, running_returns)

        # 2. Normalize returns for learning stability (Zero-mean, Unit-variance)
        returns_tensor = torch.tensor(discounted_returns)
        if len(returns_tensor) > 1:
            mean = returns_tensor.mean()
            std = returns_tensor.std() + 1e-9
            returns_tensor = (returns_tensor - mean) / std

        # 3. Objective Function: -Sum( log_prob * return )
        for log_prob, disc_return in zip(self._saved_log_probs, returns_tensor, strict=False):
            policy_loss.append(-log_prob * disc_return)

        # 4. Neural Network Optimization
        self._optimizer.zero_grad()
        loss = torch.cat(policy_loss).sum()
        loss.backward()  # type: ignore[no-untyped-call]

        # Gradient clipping to prevent policy explosion/divergence
        nn.utils.clip_grad_norm_(self._policy.parameters(), max_norm=1.0)
        self._optimizer.step()

        # 5. State Cleanup for next episode
        loss_val = float(loss.item())
        self._saved_log_probs.clear()
        self._rewards.clear()

        return loss_val
