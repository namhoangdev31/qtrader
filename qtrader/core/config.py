from __future__ import annotations

from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class QTraderSettings(BaseSettings):
    """Centralized configuration for QTrader. Loads from .env with validation at startup."""

    model_config = SettingsConfigDict(
        env_file="/Users/hoangnam/qtrader/.env",
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
    
    # Redis (Shared State)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0
    redis_prefix: str = "qtrader"

    # Execution
    impact_daily_volume: float = 1_000_000.0
    impact_sigma_daily: float = 0.02
    impact_y: float = 1.0

    # Trading System Settings
    ts_max_position_usd: float = 100_000.0
    ts_max_drawdown_pct: float = 0.20
    ts_max_order_qty: float = 1.0
    ts_max_order_notional: float = 50_000.0
    ts_max_orders_per_second: float = 5.0
    ts_max_latency_ms: float = 100.0
    
    # Model Hub
    ts_forecast_model: str = "llama3.2:1b"
    ts_risk_model: str = "qwen3.5:2b"
    ts_decision_model: str = "gemma4:e2b"
    
    # Risk & Guardrails
    ts_atr_window: int = 14
    ts_atr_multiplier: float = 2.0
    ts_forecast_multiplier: float = 1.5
    ts_min_sl_pct: float = 0.005
    ts_max_sl_pct: float = 0.05
    ts_price_jump_threshold: float = 0.05
    ts_reference_price: float = 50000.0
    
    # Retraining & Circuit Breakers
    ts_retrain_win_rate_threshold: float = 0.35
    ts_win_history_window: int = 10
    ts_min_forecast_points: int = 2
    ts_streak_reduction_threshold: int = 3
    ts_anomaly_loss_threshold: int = 3

    # Bot / Operational
    log_level: str = "INFO"
    monthly_cloud_budget: float = 1000.0
    db_path: str = "qtrader.db"
    timezone: str = "Asia/Ho_Chi_Minh"
    trading_symbols: list[str] = ["BTC/USDT", "ETH/USDT"]
    enable_auto_forensic: bool = True

    sim_taker_fee: float = 0.006
    sim_maker_fee: float = 0.004
    sim_latency_min_ms: int = 50
    sim_latency_max_ms: int = 300
    sim_error_probability: float = 0.01
    sim_slippage_vol_mult: float = 0.5
    
    # Paper Engine Limits & RSI Gates
    sim_price_history_limit: int = 5000
    sim_price_history_prune: int = 2000
    sim_min_history_for_analysis: int = 20
    sim_rsi_period: int = 14
    sim_rsi_bull_gate: float = 45.0
    sim_rsi_bear_gate: float = 55.0
    sim_rsi_oversold: float = 30.0
    sim_rsi_overbought: float = 70.0
    sim_reversal_threshold: float = 0.35
    sim_min_trade_notional: float = 10.0
    sim_epsilon_qty: float = 1e-8
    sim_thinking_history_limit: int = 100
    sim_external_tick_timeout: float = 2.0
    sim_sma_short_window: int = 5
    sim_sma_long_window: int = 10
    sim_crossover_threshold: float = 0.0001
    sim_anomaly_threshold: float = 0.01
    lifecycle_pnl_interval: float = 5.0
    lifecycle_sentiment_interval: float = 600.0
    lifecycle_health_interval: float = 10.0

    # Alert Routing
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_alerts_enabled: bool = False
    alert_email_smtp_host: str = ""
    alert_email_smtp_port: int = 587
    alert_email_sender: str = ""
    alert_email_password: str = ""
    alert_email_recipients: str = ""  # comma-separated
    alert_email_enabled: bool = False
    alert_webhook_url: str = ""
    alert_webhook_enabled: bool = False
    alert_min_severity: str = "WARNING"
    alert_cooldown_seconds: float = 60.0
    arbitrator_wt_latency: float = 1.0
    arbitrator_wt_staleness: float = 1.0

    # Clock Sync
    clock_sync_enabled: bool = True
    clock_sync_interval_s: int = 3600
    clock_sync_ntp_server: str = "pool.ntp.org"

    # JWT Security
    jwt_secret_key: str = "changeme-for-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    @property
    def TRADING_SYMBOLS(self) -> list[str]:
        return self.trading_symbols

    @model_validator(mode="after")
    def resolve_paths(self) -> QTraderSettings:
        """Ensure paths are absolute relative to project root."""
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
    def REDIS_HOST(self) -> str:
        return self.redis_host

    @property
    def REDIS_PORT(self) -> int:
        return self.redis_port

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
    def FORECAST_MODEL(self) -> str:
        return self.ts_forecast_model
    
    @property
    def RISK_MODEL(self) -> str:
        return self.ts_risk_model
    
    @property
    def DECISION_MODEL(self) -> str:
        return self.ts_decision_model

    @property
    def ENABLE_AUTO_FORENSIC(self) -> bool:
        return self.enable_auto_forensic

    @property
    def SIM_TAKER_FEE(self) -> float:
        return self.sim_taker_fee
        
    @property
    def SIM_MAKER_FEE(self) -> float:
        return self.sim_maker_fee

    @property
    def SIM_LATENCY_MIN_MS(self) -> int:
        return self.sim_latency_min_ms

    @property
    def SIM_LATENCY_MAX_MS(self) -> int:
        return self.sim_latency_max_ms

    @property
    def SIM_ERROR_PROBABILITY(self) -> float:
        return self.sim_error_probability

    @property
    def SIM_SLIPPAGE_VOL_MULT(self) -> float:
        return self.sim_slippage_vol_mult

    @property
    def SIM_PRICE_HISTORY_LIMIT(self) -> int:
        return self.sim_price_history_limit

    @property
    def SIM_PRICE_HISTORY_PRUNE(self) -> int:
        return self.sim_price_history_prune

    @property
    def SIM_MIN_HISTORY_FOR_ANALYSIS(self) -> int:
        return self.sim_min_history_for_analysis

    @property
    def SIM_RSI_PERIOD(self) -> int:
        return self.sim_rsi_period

    @property
    def SIM_RSI_BULL_GATE(self) -> float:
        return self.sim_rsi_bull_gate

    @property
    def SIM_RSI_BEAR_GATE(self) -> float:
        return self.sim_rsi_bear_gate

    @property
    def SIM_RSI_OVERSOLD(self) -> float:
        return self.sim_rsi_oversold

    @property
    def SIM_RSI_OVERBOUGHT(self) -> float:
        return self.sim_rsi_overbought

    @property
    def SIM_REVERSAL_THRESHOLD(self) -> float:
        return self.sim_reversal_threshold

    @property
    def SIM_MIN_TRADE_NOTIONAL(self) -> float:
        return self.sim_min_trade_notional

    @property
    def SIM_EPSILON_QTY(self) -> float:
        return self.sim_epsilon_qty

    @property
    def SIM_THINKING_HISTORY_LIMIT(self) -> int:
        return self.sim_thinking_history_limit

    @property
    def SIM_EXTERNAL_TICK_TIMEOUT(self) -> float:
        return self.sim_external_tick_timeout

    @property
    def SIM_SMA_SHORT_WINDOW(self) -> int:
        return self.sim_sma_short_window

    @property
    def SIM_SMA_LONG_WINDOW(self) -> int:
        return self.sim_sma_long_window

    @property
    def SIM_CROSSOVER_THRESHOLD(self) -> float:
        return self.sim_crossover_threshold

    @property
    def SIM_ANOMALY_THRESHOLD(self) -> float:
        return self.sim_anomaly_threshold

    # Removed problematic attributes: RAY_ADDRESS, RAY_MEMORY, RAY_CPUS


# Module-level singleton; validated at import (fail-fast)
settings: QTraderSettings = QTraderSettings()


class ConfigLoader:
    """Unified configuration loader for QTrader."""

    @staticmethod
    def load() -> QTraderSettings:
        return settings


# Backward compatibility alias for existing code using Config.BINANCE_API_KEY etc.
Config: QTraderSettings = settings


def build_alert_router_config() -> dict[str, Any]:
    """Build AlertRouterConfig kwargs from centralized settings.

    Returns a plain dict so the caller can construct the config without
    importing alert_router at module level (avoids circular imports).
    """
    cfg: dict[str, Any] = {
        "min_severity": settings.alert_min_severity,
        "cooldown_seconds": settings.alert_cooldown_seconds,
    }
    if settings.telegram_alerts_enabled and settings.telegram_bot_token:
        cfg["telegram"] = {
            "bot_token": settings.telegram_bot_token,
            "chat_id": settings.telegram_chat_id,
        }
    if settings.alert_email_enabled and settings.alert_email_smtp_host:
        cfg["email"] = {
            "smtp_host": settings.alert_email_smtp_host,
            "smtp_port": settings.alert_email_smtp_port,
            "sender": settings.alert_email_sender,
            "password": settings.alert_email_password,
            "recipients": [r.strip() for r in settings.alert_email_recipients.split(",") if r.strip()],
        }
    if settings.alert_webhook_enabled and settings.alert_webhook_url:
        cfg["webhook"] = {"url": settings.alert_webhook_url}
    return cfg