from __future__ import annotations

import threading
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from qtrader.core.config import settings


class ExecutionStyle(str, Enum):
    AGGRESSIVE = "AGGRESSIVE_TAKER"
    BALANCED = "BALANCED"
    PASSIVE = "PASSIVE_MAKER"


class LiveConfigSchema(BaseModel):
    min_confidence: float = Field(default=0.55, description="Required signal confidence to enter")
    exit_confidence: float = Field(
        default=0.45, description="Confidence level to trigger early exit"
    )
    signal_ema_alpha: float = Field(default=0.2, description="Smoothing for signal direction")
    min_signal_streak: int = Field(default=1, description="Required consecutive signals")
    sim_rsi_bull_gate: float = Field(default=45.0, description="RSI threshold for long entry")
    sim_rsi_bear_gate: float = Field(default=55.0, description="RSI threshold for short entry")
    sim_rsi_oversold: float = Field(default=30.0, description="RSI oversold boundary")
    sim_rsi_overbought: float = Field(default=70.0, description="RSI overbought boundary")
    sim_sma_short_window: int = Field(default=5, description="Short SMA window size")
    sim_sma_long_window: int = Field(default=10, description="Long SMA window size")
    sim_crossover_threshold: float = Field(default=0.0001, description="Min SMA delta for signal")
    sim_reversal_threshold: float = Field(
        default=0.35, description="Threshold for reversal detection"
    )
    sim_mean_reversion_strength: float = Field(
        default=0.01, description="Strength of drift towards base price"
    )
    stop_loss_pct: float = Field(default=0.025, description="Dynamic SL base percentage")
    take_profit_pct: float = Field(default=0.05, description="Dynamic TP base percentage")
    trailing_stop_activation_pct: float = Field(
        default=0.03, description="Profit level to activate trailing SL"
    )
    sim_taker_fee: float = Field(default=0.0006, description="Simulated taker fee (decimal)")
    sim_maker_fee: float = Field(default=0.0002, description="Simulated maker fee (decimal)")
    sim_latency_min_ms: float = Field(default=50.0, description="Min simulation latency")
    sim_latency_max_ms: float = Field(default=300.0, description="Max simulation latency")
    sim_slippage_vol_mult: float = Field(
        default=0.5, description="Multiplier for slippage volatility"
    )
    max_drawdown_limit: float = Field(default=0.15, description="Hard drawdown limit")
    max_consecutive_losses: int = Field(default=20, description="Circuit breaker threshold")
    execution_style: ExecutionStyle = Field(default=ExecutionStyle.BALANCED)
    position_size_pct: float = Field(default=0.2, description="Max capital allocation per trade")
    min_hold_time_s: int = Field(default=5, description="Minimum duration for a trade")
    ts_max_orders_per_second: float = Field(default=10.0, description="Rate limit (orders/sec)")
    lifecycle_sentiment_interval: float = Field(
        default=600.0, description="Sentiment refresh rate (s)"
    )
    sim_anomaly_threshold: float = Field(default=0.01, description="Price jump anomaly trigger")
    reference_price_btc: float = Field(default=71522.97, description="Simulator baseline BTC")
    reference_price_eth: float = Field(default=3500.0, description="Simulator baseline ETH")
    max_md_points: int = Field(default=5000, description="Max market data points in memory")
    md_prune_target: int = Field(default=1000, description="Points to retain on prune")
    active_strategy: str = Field(
        default="MOMENTUM", description="Currently active trading strategy"
    )
    ml_weight: float = Field(default=0.6, description="Weight for ML signals (0.0-1.0)")
    traditional_weight: float = Field(
        default=0.4, description="Weight for technical signals (0.0-1.0)"
    )
    signal_interval_s: float = Field(default=1.0, description="Signal processing tick interval")
    volatility_multiplier: float = Field(
        default=1.0, description="Scaling factor for signal thresholds"
    )
    min_history_for_alpha: int = Field(default=20, description="Min price points for ML prediction")
    current_market_price: float = Field(
        default=71522.97, description="Latest market price from WebSocket"
    )


class DynamicConfigManager:
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
        self._change_callback: Any | None = None
        self._initialized = True

    def register_callback(self, callback: Any) -> None:
        with self._lock:
            self._change_callback = callback

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
            try:
                return getattr(self._config, key.lower())
            except AttributeError:
                return getattr(self._config, key, default)

    def set_override(self, key: str, value: Any) -> None:
        old_value = self.get(key)
        with self._lock:
            self._overrides[key] = value
        if self._change_callback:
            try:
                self._change_callback(key, old_value, value)
            except Exception:
                pass

    def update(self, key: str, value: Any) -> None:
        self.set_override(key, value)

    def clear_overrides(self) -> None:
        with self._lock:
            self._overrides = {}
            if self._change_callback:
                self._change_callback("ALL", "RESTORED", "DEFAULT")

    def get_all_live(self) -> dict[str, Any]:
        full_state = self._config.model_dump()
        with self._lock:
            for k, v in self._overrides.items():
                full_state[k.lower()] = v
        return full_state


config_manager = DynamicConfigManager()


class DynamicSettingsMixin:
    @property
    def TAKER_FEE(self) -> float:
        return config_manager.get("sim_taker_fee")

    @property
    def MAKER_FEE(self) -> float:
        return config_manager.get("sim_maker_fee")

    @property
    def LATENCY_MIN_MS(self) -> float:
        return config_manager.get("sim_latency_min_ms")

    @property
    def LATENCY_MAX_MS(self) -> float:
        return config_manager.get("sim_latency_max_ms")

    @property
    def SLIPPAGE_VOL_MULT(self) -> float:
        return config_manager.get("sim_slippage_vol_mult")

    @property
    def ANOMALY_THRESHOLD(self) -> float:
        return config_manager.get("sim_anomaly_threshold")

    @property
    def RSI_BULL_GATE(self) -> float:
        return config_manager.get("sim_rsi_bull_gate")

    @property
    def RSI_BEAR_GATE(self) -> float:
        return config_manager.get("sim_rsi_bear_gate")

    @property
    def RSI_OVERSOLD(self) -> float:
        return config_manager.get("sim_rsi_oversold")

    @property
    def RSI_OVERBOUGHT(self) -> float:
        return config_manager.get("sim_rsi_overbought")

    @property
    def REVERSAL_THRESHOLD(self) -> float:
        return config_manager.get("sim_reversal_threshold")

    @property
    def SMA_SHORT_WINDOW(self) -> int:
        return config_manager.get("sim_sma_short_window")

    @property
    def SMA_LONG_WINDOW(self) -> int:
        return config_manager.get("sim_sma_long_window")

    @property
    def CROSSOVER_THRESHOLD(self) -> float:
        return config_manager.get("sim_crossover_threshold")

    @property
    def MEAN_REVERSION_STRENGTH(self) -> float:
        return config_manager.get("sim_mean_reversion_strength")

    @property
    def TS_MAX_ORDERS_PER_SECOND(self) -> float:
        return config_manager.get("ts_max_orders_per_second")

    @property
    def MARKET_PRICE(self) -> float:
        return config_manager.get("current_market_price")

    @property
    def ERROR_PROBABILITY(self) -> float:
        return settings.SIM_ERROR_PROBABILITY

    @property
    def PRICE_HISTORY_LIMIT(self) -> int:
        return settings.SIM_PRICE_HISTORY_LIMIT

    @property
    def PRICE_HISTORY_PRUNE(self) -> int:
        return settings.SIM_PRICE_HISTORY_PRUNE

    @property
    def MIN_HISTORY_FOR_ANALYSIS(self) -> int:
        return config_manager.get("min_history_for_alpha")

    @property
    def RSI_PERIOD(self) -> int:
        return settings.SIM_RSI_PERIOD

    @property
    def MIN_TRADE_NOTIONAL(self) -> float:
        return settings.SIM_MIN_TRADE_NOTIONAL

    @property
    def EPSILON_QTY(self) -> float:
        return settings.SIM_EPSILON_QTY

    @property
    def THINKING_HISTORY_LIMIT(self) -> int:
        return settings.SIM_THINKING_HISTORY_LIMIT

    @property
    def EXTERNAL_TICK_TIMEOUT(self) -> float:
        return settings.SIM_EXTERNAL_TICK_TIMEOUT
