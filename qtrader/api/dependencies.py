from __future__ import annotations

import logging
import os
from functools import lru_cache

from qtrader.ml.remote_client import RemoteAtomicTrioPipeline
from qtrader.trading_system import TradingSystem, create_trading_system

logger = logging.getLogger("qtrader.api.dependencies")
_SYS_INSTANCE: TradingSystem | None = None


@lru_cache
def get_system() -> TradingSystem:
    global _SYS_INSTANCE
    if _SYS_INSTANCE is not None:
        return _SYS_INSTANCE
    syms_str = os.getenv("QTRADER_SYMBOLS", "BTC-USD")
    symbols = syms_str.split(",")
    ml_url = os.getenv("ML_ENGINE_URL", "http://qt-ml-engine:8001")

    remote_ml = RemoteAtomicTrioPipeline(base_url=ml_url)
    _SYS_INSTANCE = create_trading_system(simulate=True, symbols=symbols, ml_pipeline=remote_ml)
    return _SYS_INSTANCE
