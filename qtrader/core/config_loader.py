from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field


class RiskConfig(BaseModel):
    """Configuration for Risk Assessment."""
    model_config = ConfigDict(frozen=True)
    
    max_drawdown: float = Field(ge=0.0, le=1.0)
    max_leverage: float = Field(ge=1.0)
    var_limit: float = Field(ge=0.0, le=1.0)
    kill_switch_enabled: bool = True


class ExecutionConfig(BaseModel):
    """Configuration for Order Execution."""
    model_config = ConfigDict(frozen=True)
    
    slippage_limit_bps: int = Field(ge=0)
    latency_budget_ms: int = Field(ge=0)
    retry_policy: Literal["exponential", "linear", "none"]
    simulated_fill: bool = False


class StrategyFeatureFlags(BaseModel):
    """Feature flags for strategy logic."""
    model_config = ConfigDict(frozen=True)
    
    hft_optimizations: bool = False
    risk_check_pre_trade: bool = True


class StrategyConfig(BaseModel):
    """Configuration for General Strategy."""
    model_config = ConfigDict(frozen=True)
    
    min_signal_strength: float = Field(ge=0.0, le=1.0)
    lookback_window: int = Field(gt=0)
    feature_flags: StrategyFeatureFlags


class InfrastructureConfig(BaseModel):
    """Operational/Resource Configuration."""
    model_config = ConfigDict(frozen=True)
    
    timeout_ms: int = Field(gt=0)
    concurrency_limit: int = Field(gt=0)
    buffer_size: int = Field(gt=0)


class QTraderConfig(BaseModel):
    """Top-level Configuration Schema."""
    model_config = ConfigDict(frozen=True)
    
    version: str
    risk: RiskConfig
    execution: ExecutionConfig
    strategy: StrategyConfig
    infrastructure: InfrastructureConfig


class ConfigLoader:
    """
    Authoritative configuration loader.
    Enforces strict validation and provides a single source of truth.
    """

    _instance: Optional[QTraderConfig] = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> QTraderConfig:
        """
        Loads and validates the configuration from a YAML file.
        If no path is provided, it defaults to qtrader/config/config_schema.yaml.
        """
        if cls._instance is not None and path is None:
            return cls._instance

        # Default path resolution
        if path is None:
            # Assumes running from project root or inside qtrader/
            current_dir = Path(__file__).parent.parent
            path = current_dir / "config" / "config_schema.yaml"

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                config = QTraderConfig.model_validate(data)
                cls._instance = config
                return config
        except Exception as e:
            # "Hard Fail" on invalid or missing configuration
            import sys
            print(f"\n[FATAL] CONFIGURATION STANDARDIZATION FAILED", file=sys.stderr)
            print(f"[REASON] {e}", file=sys.stderr)
            print(f"[ACTION] Validation required for {path}\n", file=sys.stderr)
            sys.exit(1)

    @classmethod
    def update_instance(cls, new_config: QTraderConfig) -> None:
        """
        Atomic swap of the configuration instance.
        Ensures all future calls to load() see the updated state.
        """
        cls._instance = new_config
        logger.info(f"[CONFIG] Atomic swap complete. New version: {new_config.version}")

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None
