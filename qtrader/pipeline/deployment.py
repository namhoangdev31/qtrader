"""DeploymentBridge: writes bot configuration from validated backtest results.

This module implements the DeploymentBridge class that takes a ResearchResult
and writes a BotConfig file to be used by the TradingBot.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from qtrader.backtest.tearsheet import TearsheetMetrics
    from qtrader.pipeline.research import ResearchResult

logger = logging.getLogger(__name__)


class DeploymentBridge:
    """Writes validated backtest results to a bot configuration file.

    The bridge takes a ResearchResult (which must be approved) and exports
    the relevant parameters to a YAML file at configs/bot_paper.yaml.
    """

    def __init__(self, config_path: str | Path = "configs/bot_paper.yaml") -> None:
        """Initialize the DeploymentBridge.

        Args:
            config_path: Path to the bot configuration file.
        """
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def deploy(self, result: ResearchResult) -> str:
        """Export the validated backtest result to a bot config file.

        Args:
            result: ResearchResult from a pipeline run (must be approved).

        Returns:
            Path to the written configuration file.

        Raises:
            ValueError: If the result is not approved for deployment.
        """
        if not result.approved_for_deployment:
            raise ValueError("Cannot deploy unapproved research result.")

        # Build the bot configuration from the research result and tearsheet
        config_dict: dict[str, Any] = {
            "strategy": result.strategy_name,
            "initial_capital": 100_000.0,  # Could be made configurable
            "signal_interval_s": 30,
            "rebalance_interval_s": 300,
            "vol_target": 0.1,
            "execution_algo": "twap",
            "symbols": [],  # To be filled by the user or from config
            "feature_cols": [],  # Will be filled by the bot
            # Derived from qtrader.backtest
            "signal_col": "ml_signal",  # Assuming ML signal was used
            "kelly_fraction": self._calculate_kelly_fraction(result.tearsheet),
            "max_position_size": 0.1,  # Placeholder
            "stop_loss": 0.02,  # Placeholder
            "take_profit": 0.05,  # Placeholder
        }

        # Override with any existing config if we want to preserve user settings
        existing_config = self._load_existing_config()
        if existing_config:
            # Keep user-defined symbols and feature_cols if present
            if existing_config.get("symbols"):
                config_dict["symbols"] = existing_config["symbols"]
            if existing_config.get("feature_cols"):
                config_dict["feature_cols"] = existing_config["feature_cols"]

        # Write the config
        with self.config_path.open("w") as f:
            yaml.dump(config_dict, f, default_flow_style=False)

        logger.info("Deployed bot config to %s", self.config_path)
        return str(self.config_path)

    def _calculate_kelly_fraction(self, tearsheet: TearsheetMetrics) -> float:
        """Calculate Kelly fraction from qtrader.backtest performance.

        Uses the simplified Kelly formula: f = (bp - q) / b
        where b = win/loss ratio, p = win probability, q = loss probability.

        Args:
            tearsheet: TearsheetMetrics from qtrader.backtest.

        Returns:
            Kelly fraction clipped to [0, 1].
        """
        if tearsheet.win_rate is None or tearsheet.profit_factor is None:
            return 0.0

        win_rate = tearsheet.win_rate
        loss_rate = 1.0 - win_rate
        # Profit factor = gross_profit / gross_loss
        # Let avg_win = gross_profit / (win_rate * N)
        # Let avg_loss = gross_loss / (loss_rate * N)
        # Then profit factor = (avg_win * win_rate) / (avg_loss * loss_rate)
        # So avg_win / avg_loss = profit_factor * (loss_rate / win_rate)
        # In Kelly, b = avg_win / avg_loss
        b = tearsheet.profit_factor * (loss_rate / win_rate) if win_rate > 0 else 0.0
        p = win_rate
        q = loss_rate
        kelly = (b * p - q) / b if b > 0 else 0.0
        return max(0.0, min(1.0, kelly))

    def _load_existing_config(self) -> dict[str, Any] | None:
        """Load existing configuration if it exists.

        Returns:
            Existing config as dict, or None if file does not exist.
        """
        if not self.config_path.exists():
            return None
        try:
            with self.config_path.open("r") as f:
                return yaml.safe_load(f)
        except Exception:
            # If we can't load, we ignore and write a new one
            return None


# ---------------------------------------------------------------------------
# Inline unit-test examples (doctest style)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import doctest

    doctest.testmod()

    # Example usage (not executed unless run directly)
    # bridge = DeploymentBridge()
    # result = ResearchResult(...)  # Assume approved
    # bridge.deploy(result)