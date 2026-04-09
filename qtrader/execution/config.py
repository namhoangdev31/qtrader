"""Configuration loader for execution system."""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


class ExecutionConfig:
    """Configuration for execution system."""

    def __init__(self, config_data: dict[str, Any]) -> None:
        self._data = config_data
        self.exchanges = config_data.get("exchanges", {})
        self.routing = config_data.get("routing", {})
        self.risk_limits = config_data.get("risk_limits", {})
        self.retry = config_data.get("retry", {})
        self.objective = config_data.get("objective", {})
        self.cost_model = config_data.get("cost_model", {})
        self.microstructure = config_data.get("microstructure", {})

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ExecutionConfig":
        """Load configuration from YAML file."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {yaml_path}")

        with open(path) as f:
            raw = f.read()

        # Replace environment variables ${VAR}
        raw = cls._replace_env_vars(raw)
        config_data = yaml.safe_load(raw)
        return cls(config_data)

    @staticmethod
    def _replace_env_vars(text: str) -> str:
        """Replace ${VAR} with environment variable values."""
        import re

        def replace(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))

        return re.sub(r"\$\{([^}]+)\}", replace, text)

    def get_exchange_config(self, exchange_name: str) -> dict[str, Any] | None:
        """Get configuration for a specific exchange."""
        return self.exchanges.get(exchange_name)

    def is_exchange_enabled(self, exchange_name: str) -> bool:
        """Check if an exchange is enabled."""
        config = self.get_exchange_config(exchange_name)
        return config.get("enabled", False) if config else False

    def get_routing_mode(self) -> str:
        """Get routing mode."""
        return self.routing.get("mode", "smart")

    def get_max_order_size(self) -> Decimal:
        """Get max order size as Decimal."""
        return Decimal(str(self.routing.get("max_order_size", 10000.0)))

    def get_split_size(self) -> Decimal | None:
        """Get split size as Decimal, if configured."""
        size = self.routing.get("split_size")
        return Decimal(str(size)) if size else None

    def get_retry_config(self) -> dict[str, Any]:
        """Get retry configuration."""
        return {
            "max_attempts": self.retry.get("max_attempts", 3),
            "delay_base": self.retry.get("delay_base", 0.1),
            "backoff_factor": self.retry.get("backoff_factor", 2.0),
        }
