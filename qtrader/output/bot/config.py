"""Bot configuration model and YAML loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["BotConfig"]


@dataclass(slots=True)
class BotConfig:
    """Configuration for the autonomous trading bot.

    Attributes:
        symbols: List of instrument symbols to trade.
        venues: List of venue identifiers.
        signal_interval_s: Seconds between signal generation.
        rebalance_interval_s: Seconds between portfolio rebalances.
        risk_check_interval_s: Seconds between risk limit checks.
        initial_capital: Starting capital in base currency.
        max_leverage: Maximum portfolio leverage.
        vol_target: Target annual volatility (e.g. 0.10 for 10%).
        max_drawdown_pct: Maximum allowed drawdown as fraction of HWM.
        daily_loss_usd: Maximum allowed daily loss in base currency.
        max_position_pct: Maximum single-position weight as fraction.
        strategy: Strategy name (momentum | mean_reversion | combined).
        execution_algo: Execution algorithm (market | twap | vwap | pov).
        regime_detection: Whether to use regime detection.
        auto_retrain: Whether to trigger retraining automatically.
        feature_cols: Feature column names (set at runtime from FactorEngine if empty).
    """

    symbols: list[str]
    venues: list[str]
    feature_cols: list[str] = field(default_factory=list)
    signal_interval_s: int = 60
    rebalance_interval_s: int = 300
    risk_check_interval_s: int = 10
    initial_capital: float = 100_000.0
    max_leverage: float = 1.0
    vol_target: float = 0.10
    max_drawdown_pct: float = 0.15
    daily_loss_usd: float = 5_000.0
    max_position_pct: float = 0.20
    strategy: str = "momentum"
    execution_algo: str = "market"
    regime_detection: bool = True
    auto_retrain: bool = False

    @classmethod
    def from_yaml(cls, path: str) -> BotConfig:
        """Load bot configuration from a YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            BotConfig instance populated from the file.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(p, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        return cls(
            symbols=list(data.get("symbols", [])),
            venues=list(data.get("venues", [])),
            feature_cols=list(data.get("feature_cols", [])),
            signal_interval_s=int(data.get("signal_interval_s", 60)),
            rebalance_interval_s=int(data.get("rebalance_interval_s", 300)),
            risk_check_interval_s=int(data.get("risk_check_interval_s", 10)),
            initial_capital=float(data.get("initial_capital", 100_000.0)),
            max_leverage=float(data.get("max_leverage", 1.0)),
            vol_target=float(data.get("vol_target", 0.10)),
            max_drawdown_pct=float(data.get("max_drawdown_pct", 0.15)),
            daily_loss_usd=float(data.get("daily_loss_usd", 5_000.0)),
            max_position_pct=float(data.get("max_position_pct", 0.20)),
            strategy=str(data.get("strategy", "momentum")),
            execution_algo=str(data.get("execution_algo", "market")),
            regime_detection=bool(data.get("regime_detection", True)),
            auto_retrain=bool(data.get("auto_retrain", False)),
        )


"""
# Pytest-style examples:
def test_config_from_yaml(tmp_path) -> None:
    cfg_path = tmp_path / "bot.yaml"
    cfg_path.write_text("symbols: [A, B]\\nvenues: [binance]\\ninitial_capital: 50000.0")
    cfg = BotConfig.from_yaml(str(cfg_path))
    assert cfg.symbols == ["A", "B"] and cfg.initial_capital == 50000.0
"""
