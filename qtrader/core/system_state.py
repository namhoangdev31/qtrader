from enum import Enum, auto
from typing import Optional

from loguru import logger


class SystemState(Enum):
    """Sovereign System States for QTrader."""

    INIT = auto()  # UNINITIALIZED
    READY = auto()  # INITIALIZED
    RUNNING = auto()  # RUNNING
    ERROR = auto()  # FAILED
    SHUTDOWN = auto()  # HALTED


class SystemStateManager:
    """Singleton Manager for Global System State Visibility."""

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
        """Update the global system state with audit logging."""
        logger.info(f"SYSTEM_STATE_TRANSITION | {self._state.name} -> {new_state.name}")
        self._state = new_state


# Global Proxy
state_manager = SystemStateManager()
