"""Unit tests for the StateStore."""
import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from qtrader.core.state_store import StateStore, Position, Order, RiskState, SystemState


@pytest.fixture
def event_loop():
    """Create an event loop for tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def state_store():
    """Create a StateStore instance."""
    return StateStore()


class TestStateStore:
    """Test the StateStore class."""

    @pytest.mark.asyncio
    async def test_initial_state(self, state_store):
        """Test initial state values."""
        positions = await state_store.get_positions()
        assert positions == {}
        
        portfolio_value = await state_store.get_portfolio_value()
        assert portfolio_value == Decimal('0')
        
        equity_curve = await state_store.get_equity_curve()
        assert equity_curve == []
        
        active_orders = await state_store.get_active_orders()
        assert active_orders == {}
        
        risk_state = await state_store.get_risk_state()
        assert risk_state.portfolio_var == Decimal('0')
        assert risk_state.portfolio_volatility == Decimal('0')
        assert risk_state.max_drawdown == Decimal('0')
        assert risk_state.leverage == Decimal('0')
        assert risk_state.daily_pnl == Decimal('0')

    @pytest.mark.asyncio
    async def test_set_and_get_position(self, state_store):
        """Test setting and getting a position."""
        position = Position(
            symbol="BTCUSDT",
            quantity=Decimal('1.5'),
            average_price=Decimal('30000')
        )
        
        await state_store.set_position(position)
        
        retrieved_position = await state_store.get_position("BTCUSDT")
        assert retrieved_position is not None
        assert retrieved_position.symbol == "BTCUSDT"
        assert retrieved_position.quantity == Decimal('1.5')
        assert retrieved_position.average_price == Decimal('30000')
        
        # Test getting all positions
        positions = await state_store.get_positions()
        assert len(positions) == 1
        assert "BTCUSDT" in positions
        assert positions["BTCUSDT"].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_update_position(self, state_store):
        """Test updating a position."""
        # Set initial position
        position = Position(
            symbol="BTCUSDT",
            quantity=Decimal('1.0'),
            average_price=Decimal('30000')
        )
        await state_store.set_position(position)
        
        # Update the position
        def updater(pos):
            pos.quantity += Decimal('0.5')
            pos.average_price = Decimal('31000')
        
        await state_store.update_position("BTCUSDT", updater)
        
        # Check the updated position
        updated_position = await state_store.get_position("BTCUSDT")
        assert updated_position.quantity == Decimal('1.5')
        assert updated_position.average_price == Decimal('31000')

    @pytest.mark.asyncio
    async def test_position_version_increment(self, state_store):
        """Test that version increments on state changes."""
        initial_version = state_store.get_version()
        
        position = Position(symbol="BTCUSDT", quantity=Decimal('1.0'))
        await state_store.set_position(position)
        
        after_set_version = state_store.get_version()
        assert after_set_version == initial_version + 1
        
        # Update via updater
        def updater(pos):
            pos.quantity += Decimal('1.0')
            
        await state_store.update_position("BTCUSDT", updater)
        
        after_update_version = state_store.get_version()
        assert after_update_version == after_set_version + 1

    @pytest.mark.asyncio
    async def test_portfolio_value(self, state_store):
        """Test portfolio value operations."""
        value = Decimal('100000')
        await state_store.set_portfolio_value(value)
        
        retrieved_value = await state_store.get_portfolio_value()
        assert retrieved_value == value

    @pytest.mark.asyncio
    async def test_equity_curve(self, state_store):
        """Test equity curve operations."""
        # Set entire curve
        curve = [
            (datetime.utcnow(), Decimal('10000')),
            (datetime.utcnow() + timedelta(hours=1), Decimal('10100'))
        ]
        await state_store.set_equity_curve(curve)
        
        retrieved_curve = await state_store.get_equity_curve()
        assert len(retrieved_curve) == 2
        assert retrieved_curve[0][1] == Decimal('10000')
        assert retrieved_curve[1][1] == Decimal('10100')
        
        # Append to curve
        await state_store.append_to_equity_curve(
            datetime.utcnow() + timedelta(hours=2),
            Decimal('10200')
        )
        
        appended_curve = await state_store.get_equity_curve()
        assert len(appended_curve) == 3
        assert appended_curve[2][1] == Decimal('10200')

    @pytest.mark.asyncio
    async def test_active_orders(self, state_store):
        """Test active orders operations."""
        order = Order(
            order_id="order123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal('0.5'),
            price=Decimal('30000')
        )
        
        await state_store.set_order(order)
        
        retrieved_order = await state_store.get_order("order123")
        assert retrieved_order is not None
        assert retrieved_order.order_id == "order123"
        assert retrieved_order.symbol == "BTCUSDT"
        assert retrieved_order.side == "BUY"
        assert retrieved_order.quantity == Decimal('0.5')
        
        # Test getting all orders
        orders = await state_store.get_active_orders()
        assert len(orders) == 1
        assert "order123" in orders
        
        # Test removing order
        await state_store.remove_order("order123")
        removed_order = await state_store.get_order("order123")
        assert removed_order is None
        
        # Test removing non-existent order (should not raise)
        await state_store.remove_order("nonexistent")

    @pytest.mark.asyncio
    async def test_risk_state(self, state_store):
        """Test risk state operations."""
        risk_state = RiskState(
            portfolio_var=Decimal('0.05'),
            portfolio_volatility=Decimal('0.15'),
            max_drawdown=Decimal('0.10'),
            leverage=Decimal('2.0'),
            daily_pnl=Decimal('500')
        )
        
        await state_store.set_risk_state(risk_state)
        
        retrieved_risk_state = await state_store.get_risk_state()
        assert retrieved_risk_state.portfolio_var == Decimal('0.05')
        assert retrieved_risk_state.portfolio_volatility == Decimal('0.15')
        assert retrieved_risk_state.max_drawdown == Decimal('0.10')
        assert retrieved_risk_state.leverage == Decimal('2.0')
        assert retrieved_risk_state.daily_pnl == Decimal('500')

    @pytest.mark.asyncio
    async def test_system_state_snapshot_restore(self, state_store):
        """Test snapshot and restore functionality."""
        # Set up some state
        position = Position(symbol="BTCUSDT", quantity=Decimal('1.0'))
        await state_store.set_position(position)
        
        await state_store.set_portfolio_value(Decimal('50000'))
        
        order = Order(
            order_id="order123",
            symbol="ETHUSDT",
            side="SELL",
            order_type="MARKET",
            quantity=Decimal('2.0')
        )
        await state_store.set_order(order)
        
        risk_state = RiskState(daily_pnl=Decimal('100'))
        await state_store.set_risk_state(risk_state)
        
        # Take snapshot
        snapshot = await state_store.snapshot()
        
        # Modify state
        await state_store.set_portfolio_value(Decimal('60000'))
        await state_store.remove_order("order123")
        
        # Verify state changed
        assert await state_store.get_portfolio_value() == Decimal('60000')
        assert await state_store.get_order("order123") is None
        
        # Restore from snapshot
        await state_store.restore(snapshot)
        
        # Verify state restored
        assert await state_store.get_portfolio_value() == Decimal('50000')
        restored_order = await state_store.get_order("order123")
        assert restored_order is not None
        assert restored_order.symbol == "ETHUSDT"
        assert restored_order.side == "SELL"
        
        restored_risk_state = await state_store.get_risk_state()
        assert restored_risk_state.daily_pnl == Decimal('100')

    @pytest.mark.asyncio
    async def test_concurrent_access(self, state_store):
        """Test concurrent access to the state store."""
        async def update_position_task(symbol, quantity):
            position = Position(symbol=symbol, quantity=Decimal(quantity))
            await state_store.set_position(position)
            
        async def get_position_task(symbol):
            return await state_store.get_position(symbol)
        
        # Run concurrent tasks
        tasks = [
            update_position_task("BTCUSDT", "1.0"),
            update_position_task("ETHUSDT", "2.0"),
            update_position_task("ADAUSDT", "3.0"),
            get_position_task("BTCUSDT"),
            get_position_task("ETHUSDT")
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Verify results
        btc_position = await state_store.get_position("BTCUSDT")
        eth_position = await state_store.get_position("ETHUSDT")
        ada_position = await state_store.get_position("ADAUSDT")
        
        assert btc_position.quantity == Decimal('1.0')
        assert eth_position.quantity == Decimal('2.0')
        assert ada_position.quantity == Decimal('3.0')

    @pytest.mark.asyncio
    async def test_deep_copy_isolation(self, state_store):
        """Test that returned objects are isolated from internal state."""
        position = Position(symbol="BTCUSDT", quantity=Decimal('1.0'))
        await state_store.set_position(position)
        
        # Get position and modify it
        retrieved_position = await state_store.get_position("BTCUSDT")
        retrieved_position.quantity = Decimal('999.0')
        
        # Verify internal state is unchanged
        internal_position = await state_store.get_position("BTCUSDT")
        assert internal_position.quantity == Decimal('1.0')
        assert retrieved_position.quantity == Decimal('999.0')
        
        # Test with portfolio value
        await state_store.set_portfolio_value(Decimal('50000'))
        retrieved_value = await state_store.get_portfolio_value()
        # Note: Decimal is immutable, so we can't really test isolation the same way
        # But we can verify the value is correct
        assert retrieved_value == Decimal('50000')


if __name__ == "__main__":
    pytest.main([__file__])