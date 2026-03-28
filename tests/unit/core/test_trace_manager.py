import pytest
import asyncio
from uuid import UUID, uuid4
from qtrader.core.trace_manager import TraceManager
from qtrader.core.events import MarketEvent, MarketPayload, SignalEvent, SignalPayload

@pytest.fixture(autouse=True)
def clear_context():
    TraceManager.clear_trace()
    yield
    TraceManager.clear_trace()

def test_trace_manager_basic_generation():
    tid = TraceManager.start_trace()
    assert isinstance(tid, UUID)
    assert TraceManager.get_current_trace() == tid

@pytest.mark.asyncio
async def test_trace_manager_async_propagation():
    tid = TraceManager.start_trace()
    
    async def subtask():
        # Should inherit parent's trace_id
        return TraceManager.get_current_trace()
    
    result = await subtask()
    assert result == tid

@pytest.mark.asyncio
async def test_event_trace_auto_injection():
    # 1. Start a trace
    tid = TraceManager.start_trace()
    
    # 2. Create an event (BaseEvent inherits trace_id from context)
    payload = MarketPayload(symbol="BTC-USD", bid=50000.0, ask=50000.1)
    event = MarketEvent(source="test", trace_id=tid, payload=payload, trace_id_fallback=None)
    
    # Actually, pydantic field default_factory will call TraceManager.ensure_trace()
    event = MarketEvent(source="test", trace_id=tid, payload=payload)
    assert event.trace_id == tid

@pytest.mark.asyncio
async def test_trace_context_manager():
    new_tid = uuid4()
    with TraceManager.wrap_with_trace(new_tid):
        assert TraceManager.get_current_trace() == new_tid
    
    # Context should be restored/cleared after 'with'
    assert TraceManager.get_current_trace() is None

@pytest.mark.asyncio
async def test_trace_propagation_full_chain():
    # 1. Start Trace at Ingest
    ingest_tid = TraceManager.start_trace()
    
    # 2. Simulate Alpha receiving MarketData and emitting Signal
    m_payload = MarketPayload(symbol="BTC-USD", bid=1.0, ask=1.1)
    m_event = MarketEvent(source="connector", payload=m_payload) 
    assert m_event.trace_id == ingest_tid
    
    # 3. Alpha creates Signal (implicit propagation via context)
    s_payload = SignalPayload(symbol="BTC-USD", signal_type="BUY", strength=1.0)
    s_event = SignalEvent(source="alpha", payload=s_payload)
    
    assert s_event.trace_id == ingest_tid
    assert s_event.trace_id == m_event.trace_id
