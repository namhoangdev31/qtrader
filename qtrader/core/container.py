from __future__ import annotations

import logging
from typing import Any

from qtrader.core.config_manager import ConfigManager
from qtrader.core.decimal_adapter import math_authority
from qtrader.core.fail_fast_engine import FailFastEngine
from qtrader.core.logger import qlogger
from qtrader.core.seed_manager import SeedManager
from qtrader.core.trace_authority import TraceAuthority

logger = logging.getLogger(__name__)


class Container:
    """
    Dependency Injection Container (Phase -1.5).
    Centralized authority for managing and injecting system-level singletons.
    Ensures deterministic dependency resolution and prevents direct instantiation
    of critical services in production code.
    """

    _instance: Container | None = None
    _initialized: bool = False

    def __new__(cls) -> Container:
        """Enforces singleton behavior for the DI container itself."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        # Central Registry of Core Authorities (Set S)
        self._services: dict[str, Any] = {
            "config": ConfigManager(),
            "trace": TraceAuthority,
            "logger": qlogger,
            "failfast": FailFastEngine(),
            "decimal": math_authority,
            "seed": SeedManager(
                strategy_id="qtrader_default",
                timestamp="2026-01-01T00:00:00Z",
                environment="backtest",
            ),
        }

        self._initialized = True
        logger.info(f"DI_CONTAINER_READY | Services registered: {list(self._services.keys())}")

    def get(self, service_name: str) -> Any:
        """
        Resolve and return a registered service.
        Raises KeyError if the service is not found.
        """
        if service_name not in self._services:
            logger.error(f"DI_RESOLUTION_FAILED | Unknown service requested: {service_name}")
            raise KeyError(f"Service '{service_name}' is not registered in the DI container.")

        return self._services[service_name]

    def register(self, name: str, service: Any, overwrite: bool = False) -> None:
        """
        Manually register or override a service (primarily for testing/bootstrapping).
        """
        if name in self._services and not overwrite:
            logger.error(f"DI_REGISTRATION_FAILED | Duplicate entry for: {name}")
            raise ValueError(
                f"Service '{name}' is already registered. Set overwrite=True to replace."
            )

        self._services[name] = service
        logger.info(f"DI_SERVICE_REGISTERED | Name: {name} | Type: {type(service)}")

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for unit testing purposes)."""
        cls._instance = None
        cls._initialized = False


# Global authoritative instance
container = Container()
