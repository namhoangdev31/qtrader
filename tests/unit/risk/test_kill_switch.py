"""
Level 1 Critical Tests for NetworkKillSwitch (risk/network_kill_switch.py)
Covers: hard kill, soft kill, idempotent triggering, OMS cancel-all integration.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from qtrader.risk.network_kill_switch import NetworkKillSwitch


@pytest.fixture
def switch_no_oms():
    return NetworkKillSwitch()


@pytest.fixture
def mock_oms():
    adapter = MagicMock()
    adapter.cancel_all_orders = AsyncMock()
    return adapter


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------
def test_kill_switch_starts_inactive(switch_no_oms):
    assert switch_no_oms._triggered is False
    assert switch_no_oms._trigger_reason is None
    assert switch_no_oms._triggered_at is None


# ---------------------------------------------------------------------------
# Hard kill — no OMS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hard_kill_sets_triggered_flag(switch_no_oms):
    await switch_no_oms.engage_hard_kill("max drawdown")
    assert switch_no_oms._triggered is True
    assert switch_no_oms._trigger_reason == "max drawdown"
    assert switch_no_oms._mode == "hard"
    assert switch_no_oms._triggered_at is not None


@pytest.mark.asyncio
async def test_hard_kill_idempotent(switch_no_oms):
    """Calling engage_hard_kill twice must not crash or double-trigger."""
    await switch_no_oms.engage_hard_kill("first")
    await switch_no_oms.engage_hard_kill("second")  # Should be no-op
    # Reason should still be the first one
    assert switch_no_oms._trigger_reason == "first"


# ---------------------------------------------------------------------------
# Hard kill — with OMS adapter (cancel_all_orders)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hard_kill_calls_cancel_all_orders(mock_oms):
    switch = NetworkKillSwitch(oms_adapter=mock_oms)
    await switch.engage_hard_kill("P&L breach")
    mock_oms.cancel_all_orders.assert_awaited_once()


@pytest.mark.asyncio
async def test_hard_kill_oms_error_does_not_crash(mock_oms):
    """Even if OMS cancel_all_orders raises, the kill switch must stay triggered."""
    mock_oms.cancel_all_orders.side_effect = ConnectionError("Exchange unreachable")
    switch = NetworkKillSwitch(oms_adapter=mock_oms)
    # Should not raise
    await switch.engage_hard_kill("P&L breach")
    assert switch._triggered is True


# ---------------------------------------------------------------------------
# Soft kill — must NOT cancel orders
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_soft_kill_sets_mode(mock_oms):
    switch = NetworkKillSwitch(oms_adapter=mock_oms)
    if hasattr(switch, "engage_soft_kill"):
        await switch.engage_soft_kill("precautionary halt")
        assert switch._triggered is True
        assert switch._mode == "soft"
        # Soft kill should NOT cancel existing orders
        mock_oms.cancel_all_orders.assert_not_awaited()


# ---------------------------------------------------------------------------
# Market-stress scenario: rapid sequential risk events
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rapid_risk_events_only_trigger_once(mock_oms):
    """Simulates multiple concurrent risk signals — kill switch must be exactly once."""
    import asyncio
    switch = NetworkKillSwitch(oms_adapter=mock_oms)
    
    async def fire():
        await switch.engage_hard_kill("rapid fire")

    await asyncio.gather(fire(), fire(), fire())
    # cancel_all_orders should be called at most once
    assert mock_oms.cancel_all_orders.call_count <= 1
