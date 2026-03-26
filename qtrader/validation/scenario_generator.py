from __future__ import annotations

import numpy as np
import polars as pl


class ScenarioGenerator:
    """
    Forensic Market Scenario Generator for System Robustness Validation.
    
    Produces extreme price vectors to simulate tail-risk events:
    - Flash Crash: Instantaneous 10-20% collapse.
    - Volatility Spike: Regime shift to high-sigma clusters.
    - Liquidity Collapse: Bid-Ask widening and volume depletion.
    """

    @staticmethod
    def generate_flash_crash(
        symbol: str, 
        base_price: float, 
        length: int = 100,
        crash_start: int = 40,
        crash_depth: float = 0.15
    ) -> pl.DataFrame:
        """
        Produce a deterministic flash crash scenario.
        """
        prices = np.full(length, base_price)
        # Crash Phase
        prices[crash_start:crash_start+5] *= np.linspace(1.0, 1.0 - crash_depth, 5)
        # Recovery/Trough Phase
        prices[crash_start+5:crash_start+20] *= (1.0 - crash_depth)
        # partial recovery
        prices[crash_start+20:] *= (1.0 - crash_depth * 0.5)

        timestamps = np.arange(length)
        
        return pl.DataFrame({
            "timestamp": timestamps,
            "symbol": [symbol] * length,
            "open": prices,
            "high": prices * 1.001,
            "low": prices * 0.999,
            "close": prices,
            "volume": np.random.randint(1000, 5000, length)
        })

    @staticmethod
    def generate_volatility_spike(
        symbol: str, 
        base_price: float, 
        length: int = 100,
        spike_start: int = 30,
        sigma_multiplier: float = 5.0
    ) -> pl.DataFrame:
        """
        Produce a regime-shift volatility cluster.
        """
        returns = np.random.normal(0, 0.001, length)
        # Spike volatility
        returns[spike_start:] *= sigma_multiplier
        
        prices = base_price * np.exp(np.cumsum(returns))
        timestamps = np.arange(length)
        
        return pl.DataFrame({
            "timestamp": timestamps,
            "symbol": [symbol] * length,
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": np.random.randint(100, 1000, length)
        })
