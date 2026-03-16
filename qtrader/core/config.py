"""Central configuration via Pydantic Settings with validation and env loading."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["QTraderSettings", "settings", "Config"]


class QTraderSettings(BaseSettings):
    """Centralized configuration for QTrader. Loads from .env with validation at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # Coinbase
    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""
    coinbase_rest_base: str = "https://api.coinbase.com/api/v3"
    coinbase_key_name: str = ""
    coinbase_private_key: str = ""

    # Data Lake
    datalake_uri: str = "data_lake"
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    
    # ML
    mlflow_tracking_uri: str = "http://localhost:5050"
    mlflow_experiment_name: str = "qtrader_v4_autonomous"
    simulate_mode: bool = True
    
    # PostgreSQL
    database_url: str = "postgresql://sanauto:secret@localhost:5432/qtrader"
    database_read_url: str | None = None  # Read replica; falls back to database_url if unset
    database_max_connections: int = 100
    database_ssl_enabled: bool = False
    
    # Execution
    impact_daily_volume: float = 1_000_000.0
    impact_sigma_daily: float = 0.02
    impact_y: float = 1.0
    
    # Bot / Operational
    log_level: str = "INFO"
    monthly_cloud_budget: float = 1000.0
    db_path: str = "qtrader.db"
    timezone: str = "Asia/Ho_Chi_Minh"

    @model_validator(mode="after")
    def resolve_paths(self) -> QTraderSettings:
        """Ensure paths are absolute relative to project root."""
        import os
        from pathlib import Path
        
        # Find project root (where .env or .git exists, or just parent of qtrader/)
        root = Path(__file__).parent.parent.parent
        
        if not Path(self.datalake_uri).is_absolute():
            self.datalake_uri = str((root / self.datalake_uri).resolve())
            
        if not Path(self.db_path).is_absolute():
            self.db_path = str((root / self.db_path).resolve())
            
        return self

    @model_validator(mode="after")
    def validate_live_mode(self) -> QTraderSettings:
        """If simulate_mode=False, require at least one exchange API key (fail-fast)."""
        if not self.simulate_mode:
            if not self.binance_api_key and not self.coinbase_api_key:
                raise ValueError(
                    "Live mode requires at least one exchange API key. "
                    "Set BINANCE_API_KEY or COINBASE_API_KEY in .env."
                )
        return self

    # Backward compatibility: uppercase aliases for existing code (Config.BINANCE_API_KEY etc.)
    @property
    def BINANCE_API_KEY(self) -> str:
        return self.binance_api_key

    @property
    def BINANCE_API_SECRET(self) -> str:
        return self.binance_api_secret

    @property
    def COINBASE_API_KEY(self) -> str:
        return self.coinbase_api_key

    @property
    def COINBASE_API_SECRET(self) -> str:
        return self.coinbase_api_secret

    @property
    def COINBASE_REST_BASE(self) -> str:
        return self.coinbase_rest_base

    @property
    def COINBASE_KEY_NAME(self) -> str:
        return self.coinbase_key_name

    @property
    def COINBASE_PRIVATE_KEY(self) -> str:
        return self.coinbase_private_key

    @property
    def DATALAKE_URI(self) -> str:
        return self.datalake_uri

    @property
    def S3_ENDPOINT(self) -> str:
        return self.s3_endpoint

    @property
    def S3_ACCESS_KEY(self) -> str:
        return self.s3_access_key

    @property
    def S3_SECRET_KEY(self) -> str:
        return self.s3_secret_key

    @property
    def MLFLOW_URI(self) -> str:
        return self.mlflow_tracking_uri

    @property
    def MLFLOW_EXPERIMENT_NAME(self) -> str:
        return self.mlflow_experiment_name

    @property
    def SIMULATE_MODE(self) -> bool:
        return self.simulate_mode

    @property
    def DB_URL(self) -> str:
        return self.database_url

    @property
    def DB_MAX_CONN(self) -> int:
        return self.database_max_connections

    @property
    def DB_SSL(self) -> bool:
        return self.database_ssl_enabled

    @property
    def DB_PATH(self) -> str:
        return self.db_path

    @property
    def IMPACT_DAILY_VOLUME(self) -> float:
        return self.impact_daily_volume

    @property
    def IMPACT_SIGMA_DAILY(self) -> float:
        return self.impact_sigma_daily

    @property
    def IMPACT_Y(self) -> float:
        return self.impact_y

    @property
    def LOG_LEVEL(self) -> str:
        return self.log_level

    @property
    def MONTHLY_BUDGET(self) -> float:
        return self.monthly_cloud_budget

    @property
    def RAY_ADDRESS(self) -> str:
        return self.ray_address

    @property
    def RAY_MEMORY(self) -> str:
        return self.ray_memory

    @property
    def RAY_CPUS(self) -> int:
        return self.ray_cpus

    @property
    def TIMEZONE(self) -> str:
        return self.timezone

    @property
    def tz(self):
        """Returns the tzinfo object (ZoneInfo)."""
        import zoneinfo
        return zoneinfo.ZoneInfo(self.timezone)


# Module-level singleton; validated at import (fail-fast)
settings: QTraderSettings = QTraderSettings()

# Backward compatibility alias for existing code using Config.BINANCE_API_KEY etc.
Config: QTraderSettings = settings


"""
# Pytest-style examples:
def test_settings_validates_live_mode_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("SIMULATE_MODE", "false")
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("COINBASE_API_KEY", raising=False)
    from pydantic_settings import BaseSettings
    # Re-import to get fresh validation; in practice use pytest fixture to clear cache
    with pytest.raises(ValueError, match="Live mode requires"):
        QTraderSettings()

def test_settings_loads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = QTraderSettings()
    assert s.log_level == "DEBUG"
"""
