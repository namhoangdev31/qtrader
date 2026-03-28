from __future__ import annotations

import hashlib
import random
import zlib
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import torch
from loguru import logger


@dataclass(slots=True)
class SeedManager:
    """
    Global Entropy Control System for deterministic execution.
    
    Enforces reproducible randomness across random, numpy, and torch
    using a multi-tiered derivation model.
    """

    strategy_id: str
    timestamp: str
    environment: str
    global_seed: int = 0
    _is_applied: bool = False

    def __post_init__(self) -> None:
        """Initialize and compute the global entropy anchor."""
        self.global_seed = self._compute_global_seed()
        logger.info(f"[SEED] Entropy Anchor Initialized | Global Seed: {self.global_seed}")

    def _compute_global_seed(self) -> int:
        """
        Compute the global anchor seed using SHA256.
        Formula: seed = int(SHA256(strategy_id || timestamp || environment)[:8], 16)
        """
        entropy_string = f"{self.strategy_id}-{self.timestamp}-{self.environment}"
        hash_digest = hashlib.sha256(entropy_string.encode()).hexdigest()
        # Use first 8 chars (32-bit) for high compatibility across all libraries
        return int(hash_digest[:8], 16)

    def get_module_seed(self, module_name: str) -> int:
        """
        Derive a deterministic sub-seed for a specific module.
        Formula: seed_i = (global_seed XOR adler32(module_name))
        """
        module_salt = zlib.adler32(module_name.encode())
        return (self.global_seed ^ module_salt) & 0xFFFFFFFF

    def apply_global(self) -> dict[str, Any]:
        """
        Inject the global seed into all supported stochastic libraries.
        This freezes the entropy state for the current process.
        """
        if self._is_applied:
            logger.warning("[SEED] Re-application of global seed attempted. Ignition blocked.")
            return self._get_status()

        # 1. Standard Library
        random.seed(self.global_seed)

        # 2. NumPy
        np.random.seed(self.global_seed)

        # 3. PyTorch
        torch.manual_seed(self.global_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.global_seed)

        # 4. Deterministic algorithms (CuDNN etc)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

        self._is_applied = True
        logger.success(f"[SEED] Deterministic Fortress Engaged | Modules seeded: random, numpy, torch")
        
        return self._get_status()

    def _get_status(self) -> dict[str, Any]:
        """Return the current seeding state."""
        return {
            "status": "DETERMINISTIC" if self._is_applied else "UNCONTROLLED",
            "global_seed": self.global_seed,
            "environment": self.environment,
            "applied": self._is_applied
        }

    @classmethod
    def from_config(cls, strategy_id: str, timestamp: str, simulate_mode: bool) -> SeedManager:
        """Factory method to build SeedManager from environment state."""
        env = "backtest" if simulate_mode else "live"
        return cls(strategy_id=strategy_id, timestamp=timestamp, environment=env)
