import datetime
from unittest.mock import MagicMock

import pytest

from qtrader.core.event import MarketDataEvent
from qtrader.core.event_bus import EventBus
from qtrader.data.quality_gate import DataQualityError, DataQualityGate


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    return bus

def test_quality_gate_mad_outlier_rejection(mock_bus):
    gate = DataQualityGate(event_bus=mock_bus)
    
    # Normal distribution around 50000
    recent_prices = [50000 + i for i in range(20)]
    
    # Outlier at 60000
    event = MarketDataEvent(
        symbol="BTC-USDT",
        data={"last_price": 60000.0, "venue": "binance"},
        metadata={"venue": "binance"},
        trace_id="t-outlier"
    )
    
    is_valid = gate.validate(event, recent_prices, z_threshold=3.0)
    
    assert is_valid is False

def test_quality_gate_cross_exchange_rejection(mock_bus):
    gate = DataQualityGate(event_bus=mock_bus)
    Recent_prices = [50000 + i for i in range(20)]
    
    # Binance price is 55000, Coinbase ref price is 50000 (10% deviation)
    event = MarketDataEvent(
        symbol="BTC-USDT",
        data={"last_price": 55000.0},
        metadata={"venue": "binance"},
        trace_id="t-deviant"
    )
    
    # Epsilon 5%
    is_valid = gate.validate(event, Recent_prices, ref_price=50000.0, epsilon_pct=0.05)
    
    assert is_valid is False

def test_quality_gate_valid_data(mock_bus):
    gate = DataQualityGate(event_bus=mock_bus)
    Recent_prices = [50000 + i for i in range(20)]
    
    # Normal price
    event = MarketDataEvent(
        symbol="BTC-USDT",
        data={"last_price": 50005.0},
        metadata={"venue": "binance"},
        trace_id="t-valid"
    )
    
    is_valid = gate.validate(event, Recent_prices, ref_price=50004.0)
    
    assert is_valid is True

def test_check_stale():
    import time
    # Fresh data
    DataQualityGate.check_stale(time.time() * 1000, max_age_ms=5000)
    
    # Old data
    with pytest.raises(DataQualityError):
        DataQualityGate.check_stale((time.time() - 10) * 1000, max_age_ms=5000)
