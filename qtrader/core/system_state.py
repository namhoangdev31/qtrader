from enum import Enum, auto
from typing import Optional

from loguru import logger


class SystemState(Enum):
    INIT = auto()
    READY = auto()
    RUNNING = auto()
    ERROR = auto()
    SHUTDOWN = auto()


class SystemStateManager:
    _instance: Optional["SystemStateManager"] = None
    _state: SystemState = SystemState.INIT

    def __new__(cls) -> "SystemStateManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def state(self) -> SystemState:
        return self._state

    def set_state(self, new_state: SystemState) -> None:
        logger.info(f"SYSTEM_STATE_TRANSITION | {self._state.name} -> {new_state.name}")
        self._state = new_state


state_manager = SystemStateManager()
