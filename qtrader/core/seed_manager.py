from __future__ import annotations

import hashlib
import random
import zlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from loguru import logger


@dataclass(slots=True)
class SeedManager:
    strategy_id: str
    timestamp: str
    environment: str
    global_seed: int = 0
    _is_applied: bool = False

    def is_applied(self) -> bool:
        return self._is_applied

    def is_applied_method(self) -> bool:
        return self._is_applied

    def __post_init__(self) -> None:
        self.global_seed = self._compute_global_seed()
        logger.info(f"[SEED] Entropy Anchor Initialized | Global Seed: {self.global_seed}")

    def _compute_global_seed(self) -> int:
        entropy_string = f"{self.strategy_id}-{self.timestamp}-{self.environment}"
        hash_digest = hashlib.sha256(entropy_string.encode()).hexdigest()
        return int(hash_digest[:8], 16)

    def get_module_seed(self, module_name: str) -> int:
        module_salt = zlib.adler32(module_name.encode())
        return (self.global_seed ^ module_salt) & 4294967295

    def apply_global(self) -> dict[str, Any]:
        if self._is_applied:
            logger.warning("[SEED] Re-application of global seed attempted. Ignition blocked.")
            return self._get_status()
        random.seed(self.global_seed)
        np.random.seed(self.global_seed)
        try:
            import torch

            torch.manual_seed(self.global_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.global_seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        except ImportError:
            logger.debug("[SEED] PyTorch not available — skipping torch seeding")
        self._is_applied = True
        logger.success(
            "[SEED] Deterministic Fortress Engaged | Modules seeded: random, numpy, torch"
        )
        return self._get_status()

    def _get_status(self) -> dict[str, Any]:
        return {
            "status": "DETERMINISTIC" if self._is_applied else "UNCONTROLLED",
            "global_seed": self.global_seed,
            "environment": self.environment,
            "applied": self._is_applied,
        }

    @classmethod
    def from_config(cls, strategy_id: str, timestamp: str, simulate_mode: bool) -> SeedManager:
        env = "backtest" if simulate_mode else "live"
        return cls(strategy_id=strategy_id, timestamp=timestamp, environment=env)
