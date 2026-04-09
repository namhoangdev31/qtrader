from collections import deque
from typing import Any
import numpy as np


class ExperienceReplayBuffer:
    def __init__(self, capacity: int = 100000) -> None:
        self._buffer: deque[tuple[Any, ...]] = deque(maxlen=capacity)

    def add(
        self, state: list[float], action: int, reward: float, next_state: list[float], done: bool
    ) -> None:
        self._buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> list[tuple[Any, ...]]:
        return np.random.choice(self._buffer, min(len(self._buffer), batch_size))

    def __len__(self) -> int:
        return len(self._buffer)
