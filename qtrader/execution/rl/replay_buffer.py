import random
from collections import deque
from typing import Any


class ExperienceReplayBuffer:
    """
    Experience Replay Buffer for Reinforcement Learning.

    Stores transitions (S, A, R, S', Done) to decouple agent interaction
    from policy updates. This reduces temporal correlation in the training
    data and significantly improves the stability of the Policy Gradient.
    """

    def __init__(self, capacity: int = 100000) -> None:
        """
        Initialize the circular buffer with a fixed maximum capacity.

        Args:
            capacity: Maximum number of transitions to store before FIFO eviction.
        """
        # deque handles the FIFO eviction (maxlen) at the C-level for performance.
        self._buffer: deque[tuple[Any, ...]] = deque(maxlen=capacity)

    def add(
        self,
        state: list[float],
        action: int,
        reward: float,
        next_state: list[float],
        done: bool,
    ) -> None:
        """
        Append a new transition to the replay buffer.

        Args:
            state: Current market-state feature vector.
            action: Action index selected by the agent.
            reward: Scalar feedback from the environment.
            next_state: Resulting market-state feature vector.
            done: Flag indicating episode termination.
        """
        self._buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> list[tuple[Any, ...]]:
        """
        Randomly sample a batch of transitions for experience replay.

        Args:
            batch_size: Number of transitions to return.

        Returns:
            List of transition tuples.
        """
        return random.sample(self._buffer, min(len(self._buffer), batch_size))

    def __len__(self) -> int:
        """
        Return the current number of transitions stored in the buffer.
        """
        return len(self._buffer)
