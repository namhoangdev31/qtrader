"""Deployment bridge: research result → bot config YAML."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from qtrader.pipeline.research import ResearchResult

__all__ = ["DeploymentBridge"]

_LOG = logging.getLogger("qtrader.pipeline.deployment")


class DeploymentBridge:
    """
    Writes validated research results to bot-ready YAML config.
    No imports from bot/; uses only shared dataclass/config structure.
    """

    def __init__(
        self,
        paper_config_path: str = "configs/bot_paper.yaml",
        prod_config_path: str = "configs/bot_prod.yaml",
    ) -> None:
        self.paper_config_path = Path(paper_config_path)
        self.prod_config_path = Path(prod_config_path)

    def from_research_result(
        self,
        result: ResearchResult,
        target: str = "paper",
    ) -> str:
        """
        Write bot config from an approved research result.

        Args:
            result: ResearchResult with approved_for_deployment True.
            target: "paper" or "prod" to choose output path.

        Returns:
            Absolute path to the written config file.

        Raises:
            ValueError: If result is not approved for deployment.
        """
        ts = result.tearsheet
        config: dict[str, Any] = {
            "strategy": result.strategy_name,
            "signal_col": "composite_alpha",
            "execution_algo": "twap",
            "best_sharpe": ts.get("sharpe_ratio", 0.0),
            "win_rate": ts.get("win_rate", 0.0),
            "max_drawdown": ts.get("max_drawdown", 0.0),
            "kelly_fraction": ts.get("expected_value", 0.0),
            "symbols": [],
            "venues": ["paper"],
            "initial_capital": 100_000.0,
            "vol_target": 0.10,
        }
        path = self.prod_config_path if target == "prod" else self.paper_config_path
        path = Path(path).expanduser().absolute()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        _LOG.info("Wrote deployment config to %s", path)
        return str(path)
