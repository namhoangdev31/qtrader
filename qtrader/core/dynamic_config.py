from __future__ import annotations

import threading
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStyle(str, Enum):
    AGGRESSIVE = "AGGRESSIVE_TAKER"
    BALANCED = "BALANCED"
    PASSIVE = "PASSIVE_MAKER"


class LiveConfigSchema(BaseModel):
    """Schema for all AI-controllable system parameters."""

    # Confidence & Signals
    min_confidence: float = Field(default=0.55, description="Required signal confidence to enter")
    exit_confidence: float = Field(default=0.45, description="Confidence level to trigger early exit")
    signal_ema_alpha: float = Field(default=0.2, description="Smoothing for signal direction")
    min_signal_streak: int = Field(default=1, description="Required consecutive signals")

    # Risk & Protection
    stop_loss_pct: float = Field(default=0.025, description="Dynamic SL base percentage")
    take_profit_pct: float = Field(default=0.05, description="Dynamic TP base percentage")
    trailing_stop_activation_pct: float = Field(default=0.03, description="Profit level to activate trailing SL")
    max_drawdown_limit: float = Field(default=0.15, description="Hard drawdown limit")
    max_consecutive_losses: int = Field(default=20, description="Circuit breaker threshold")

    # Execution & Sizing
    execution_style: ExecutionStyle = Field(default=ExecutionStyle.BALANCED)
    position_size_pct: float = Field(default=0.20, description="Max capital allocation per trade")
    min_hold_time_s: int = Field(default=5, description="Minimum duration for a trade")
    
    # Simulation & Baseline
    sim_latency_ms_range: tuple[float, float] = Field(default=(50.0, 300.0))
    sim_slippage_bps: float = Field(default=5.0)
    reference_price_btc: float = Field(default=65000.0, description="Simulator baseline BTC")
    reference_price_eth: float = Field(default=3500.0, description="Simulator baseline ETH")
    
    # Memory & Performance
    max_md_points: int = Field(default=5000, description="Max market data points in memory")
    md_prune_target: int = Field(default=1000, description="Points to retain on prune")
    
    # Strategy & Engine
    ml_weight: float = Field(default=0.6, description="Weight for ML signals (0.0-1.0)")
    traditional_weight: float = Field(default=0.4, description="Weight for technical signals (0.0-1.0)")
    signal_interval_s: float = Field(default=1.0, description="Signal processing tick interval")
    volatility_multiplier: float = Field(default=1.0, description="Scaling factor for signal thresholds")
    min_history_for_alpha: int = Field(default=20, description="Min price points for ML prediction")


class DynamicConfigManager:
    """Manages system configuration with real-time AI overrides."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._config = LiveConfigSchema()
        self._overrides: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._initialized = True

    def get(self, key: str, default: Any = None) -> Any:
        """Get parameter value, prioritizing AI overrides."""
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
            
            # Try to get from Pydantic model
            try:
                return getattr(self._config, key.lower())
            except AttributeError:
                # Fallback for keys that might not match exact naming
                return getattr(self._config, key, default)

    def set_override(self, key: str, value: Any) -> None:
        """Apply an AI or manual override."""
        with self._lock:
            # Validate if possible (basic type check)
            self._overrides[key] = value

    def clear_overrides(self) -> None:
        """Reset all dynamic shifts to defaults."""
        with self._lock:
            self._overrides = {}

    def get_all_live(self) -> dict[str, Any]:
        """Returns the current effective configuration state."""
        full_state = self._config.model_dump()
        with self._lock:
            for k, v in self._overrides.items():
                full_state[k.lower()] = v
        return full_state


# Global singleton
config_manager = DynamicConfigManager()
