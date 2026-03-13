import asyncio
import logging
from typing import Any

from qtrader.ml.regime import RegimeDetector
from qtrader.ml.registry import ModelRegistry
from qtrader.ml.rotation import ModelRotator


class AutonomousLoop:
    """
    The 'Brain' of QTrader v4.
    Runs periodically to detect market regime shifts and rotate models.
    """
    
    def __init__(
        self, 
        detector: RegimeDetector, 
        rotator: ModelRotator, 
        registry: ModelRegistry
    ) -> None:
        self.detector = detector
        self.rotator = rotator
        self.registry = registry
        self.interval = 3600 # Run every hour (for mid-term regimes)

    async def run_step(self, recent_data: Any, feature_cols: list[str]) -> None:
        """One iteration of the autonomous intelligence loop."""
        # 1. Detect current regime
        regimes = self.detector.predict_regime(recent_data, feature_cols)
        current_regime = int(regimes.tail(1)[0])
        
        # 2. Trigger rotation if needed
        target_model_id = self.rotator.on_regime_change(current_regime)
        
        # 3. If rotation happened, load new model from Registry (simulated)
        if target_model_id:
            logging.info(f"AUTONOMOUS | Finalizing rotation to model: {target_model_id}")
            # model = self.registry.load_model(target_model_id)
            # strategy.update_model(model)

    async def start(self, get_data_func: Any, feature_cols: list[str]):
        """Continuous execution of the autonomous loop."""
        while True:
            data = await get_data_func()
            await self.run_step(data, feature_cols)
            await asyncio.sleep(self.interval)
