from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.execution.rl.agent import RLOrderExecutionAgent
    from qtrader.execution.rl.replay_buffer import ExperienceReplayBuffer


_LOG = logging.getLogger("qtrader.execution.rl.training")


class RLTrainingPipeline:
    """
    RL Training Pipeline for Execution Agents.

    Orchestrates the lifecycle of Reinforcement Learning: loading historical replay data,
    simulating agent interaction, collecting rewards, and optimizing policy parameters.
    """

    def __init__(
        self,
        agent: RLOrderExecutionAgent,
        replay_buffer: ExperienceReplayBuffer,
        batch_size: int = 32,
    ) -> None:
        """
        Initialize the pipeline with the target Agent and Experience Buffer.

        Args:
            agent: The RL Agent to be trained.
            replay_buffer: Buffer for transition storage and sampling.
            batch_size: Number of transitions to sample for stochastic updates.
        """
        self._agent = agent
        self._replay_buffer = replay_buffer
        self._batch_size = batch_size

    def run_episode(self, episode_steps: list[dict[str, Any]]) -> float:
        """
        Execute a single simulation episode and store transitions to the buffer.

        Args:
            episode_steps: A sequence of market-state dictionaries for replay.

        Returns:
            Cumulative reward achieved during the episode.
        """
        min_steps = 2
        if len(episode_steps) < min_steps:
            return 0.0

        total_reward = 0.0

        for i in range(len(episode_steps) - 1):
            curr_step = episode_steps[i]
            next_step = episode_steps[i + 1]

            # 1. State Observation
            state = curr_step.get("state", [])

            # 2. Action Selection
            # Stochastic mode enabled to ensure multi-venue exploration during training.
            action = self._agent.act(state, deterministic=False)

            # 3. Environmental Feedback (Replay/Simulation)
            # In industrial production, this interfaces with the TickEngine/BrokerSim.
            reward = float(curr_step.get("reward", 0.0))
            next_state = next_step.get("state", [])
            done = i == len(episode_steps) - 2

            # 4. Experience Collection
            self._replay_buffer.add(state, action, reward, next_state, done)
            self._agent.record_reward(reward)

            total_reward += reward

        # 5. On-Policy Update Trigger
        # For REINFORCE, we update at the end of each episode trajectory.
        loss = self._agent.update()

        _LOG.debug(f"Episode complete. Reward: {total_reward:.4f}, Policy Loss: {loss:.6f}")

        return total_reward

    def train(self, dataset: list[list[dict[str, Any]]], n_epochs: int = 10) -> list[float]:
        """
        Perform batch training over multi-episode historical datasets.

        Args:
            dataset: A nested list of episodes, each containing a sequence of steps.
            n_epochs: Total number of complete passes over the dataset.

        Returns:
            List of average episode rewards per epoch for convergence tracking.
        """
        if not dataset:
            return []

        rewards_history: list[float] = []

        for epoch in range(n_epochs):
            cumulative_epoch_reward = 0.0

            for episode in dataset:
                reward = self.run_episode(episode)
                cumulative_epoch_reward += reward

            avg_reward = cumulative_epoch_reward / len(dataset)
            rewards_history.append(avg_reward)

            _LOG.info(f"Epoch {epoch + 1}/{n_epochs} | Avg Reward: {avg_reward:.4f}")

        return rewards_history
