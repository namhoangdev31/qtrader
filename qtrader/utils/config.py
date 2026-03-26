from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration management for the QTrader system."""

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        # Example: load database URL, API keys, etc.
        self._config['database_url'] = os.getenv('DATABASE_URL', 'sqlite:///qtrader.db')
        self._config['api_key'] = os.getenv('API_KEY', '')
        self._config['api_secret'] = os.getenv('API_SECRET', '')
        self._config['log_level'] = os.getenv('LOG_LEVEL', 'INFO')
        self._config['environment'] = os.getenv('ENVIRONMENT', 'development')
        # Trading parameters
        self._config['max_leverage'] = float(os.getenv('MAX_LEVERAGE', '3.0'))
        self._config['risk_limit_var'] = float(os.getenv('RISK_LIMIT_VAR', '0.02'))
        self._config['daily_loss_limit'] = float(os.getenv('DAILY_LOSS_LIMIT', '0.05'))
        # Add more as needed

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: The configuration key.
            default: The default value if the key is not found.

        Returns:
            The configuration value.
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.

        Args:
            key: The configuration key.
            value: The value to set.
        """
        self._config[key] = value

    def to_dict(self) -> dict[str, Any]:
        """
        Get a copy of the entire configuration as a dictionary.

        Returns:
            A dictionary containing all configuration values.
        """
        return self._config.copy()


# Global configuration instance
config = Config()