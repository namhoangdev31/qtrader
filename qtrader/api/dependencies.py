"""FastAPI Dependencies for QTrader.

Instantiates and manages the singleton TradingSystem.
"""

from __future__ import annotations

import logging

import os
from functools import lru_cache

from qtrader.trading_system import TradingSystem, create_trading_system

logger = logging.getLogger("qtrader.api.dependencies")

# Singleton instance of the Trading System for the API
_SYS_INSTANCE: TradingSystem | None = None

@lru_cache()
def get_system() -> TradingSystem:
    """Dependency to inject the active TradingSystem instance."""
    # Use environment for symbols
    syms_str = os.getenv("QTRADER_SYMBOLS", "BTC-USD")
    symbols = syms_str.split(",")
    
    # Dashboard uses Remote ML to stay lightweight
    ml_url = os.getenv("ML_ENGINE_URL", "http://ml-engine:8001")
    from qtrader.ml.remote_client import RemoteAtomicTrioPipeline
    remote_ml = RemoteAtomicTrioPipeline(base_url=ml_url)
    
    return create_trading_system(simulate=True, symbols=symbols, ml_pipeline=remote_ml)
