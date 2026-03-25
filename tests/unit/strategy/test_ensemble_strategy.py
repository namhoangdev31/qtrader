import pytest
from qtrader.core.types import SignalEvent, Side, MarketData
from qtrader.strategy.ensemble_strategy import EnsembleStrategy
from datetime import datetime
import polars as pl
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

def test_ensemble_strategy_initialization():
    mock_strategy1 = MagicMock()
    mock_strategy2 = MagicMock()
    ensemble = EnsembleStrategy(strategies=[mock_strategy1, mock_strategy2])
    assert len(ensemble.strategies) == 2
    assert ensemble._strategy_weights[0] == 0.5

@pytest.mark.asyncio
async def test_ensemble_strategy_generate_signals():
    mock_strategy1 = MagicMock()
    mock_strategy1.compute_signals.return_value = SignalEvent(
        symbol="BTC", signal_type="BUY", strength=1.0, timestamp=datetime.utcnow(), metadata={"buy_prob": 1.0, "sell_prob": 0.0, "hold_prob": 0.0}
    )
    
    mock_strategy2 = MagicMock()
    mock_strategy2.compute_signals.return_value = SignalEvent(
        symbol="BTC", signal_type="SELL", strength=0.5, timestamp=datetime.utcnow(), metadata={"buy_prob": 0.0, "sell_prob": 1.0, "hold_prob": 0.0}
    )
    
    ensemble = EnsembleStrategy(strategies=[mock_strategy1, mock_strategy2])
    features = {"alpha1": pl.Series([1.0])}
    signal = ensemble.compute_signals(features)
    
    assert signal.signal_type == "ENSEMBLE"
    # Combined strength logic in ensemble_strategy.py:
    # buy_prob = 0.5 * 1.0 + 0.5 * 0.0 = 0.5
    # sell_prob = 0.5 * 0.0 + 0.5 * 1.0 = 0.5
    # strength = max(0.5, 0.5, 0.0) - 0.333... = 0.166... * 1.5 = 0.25
    assert float(signal.strength) == pytest.approx(0.25)

