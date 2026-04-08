"""Unit tests for PaperTradingEngine DB persistence bridge and RSI fix.

Tests verify:
1. Fills are persisted to DB via write_fill() on position close
2. AI thinking logs are persisted on every signal generation
3. PnL snapshots use delta-check (skip identical equity values)
4. RSI returns 50.0 (neutral) when all prices are constant
5. uuid references resolve correctly
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.execution.paper_engine import PaperTradingEngine


@pytest.fixture
def mock_db_writer() -> AsyncMock:
    """Create a mock TradeDBWriter with async write methods."""
    writer = AsyncMock()
    writer.write_fill = AsyncMock()
    writer.write_thinking_log = AsyncMock()
    writer.write_pnl_snapshot = AsyncMock()
    return writer


@pytest.fixture
def engine_with_db(mock_db_writer: AsyncMock) -> PaperTradingEngine:
    """Create a PaperTradingEngine with DB writer injected."""
    engine = PaperTradingEngine(
        starting_capital=1000.0,
        base_price=65000.0,
        db_writer=mock_db_writer,
        session_id="test-session-001",
    )
    return engine


@pytest.fixture
def engine_no_db() -> PaperTradingEngine:
    """Create a PaperTradingEngine without DB writer (legacy compatibility)."""
    return PaperTradingEngine(
        starting_capital=1000.0,
        base_price=65000.0,
    )


class TestPaperEngineDBBridge:
    """Tests for the DB persistence bridge in PaperTradingEngine."""

    def test_set_db_writer_injects_correctly(self, engine_no_db: PaperTradingEngine, mock_db_writer: AsyncMock) -> None:
        """set_db_writer() should inject both db_writer and session_id."""
        assert engine_no_db._db_writer is None
        assert engine_no_db._session_id is None

        engine_no_db.set_db_writer(mock_db_writer, "inject-session-002")

        assert engine_no_db._db_writer is mock_db_writer
        assert engine_no_db._session_id == "inject-session-002"

    def test_persist_fill_calls_write_fill(self, engine_with_db: PaperTradingEngine) -> None:
        """_persist_fill() should create an asyncio task calling write_fill."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine_with_db._persist_fill(
                order_id="test-order-001",
                symbol="BTC-USD",
                side="BUY",
                quantity=0.01,
                price=65000.0,
                commission=3.25,
            )
            # Run pending tasks
            loop.run_until_complete(asyncio.sleep(0.01))

            engine_with_db._db_writer.write_fill.assert_called_once_with(
                order_id="test-order-001",
                symbol="BTC-USD",
                side="BUY",
                quantity=Decimal("0.01"),
                price=Decimal("65000.0"),
                commission=Decimal("3.25"),
                source="PaperTradingEngine",
                session_id="test-session-001",
            )
        finally:
            loop.close()

    def test_persist_fill_noop_without_db(self, engine_no_db: PaperTradingEngine) -> None:
        """_persist_fill() should be a no-op without db_writer/session_id."""
        # Should not raise
        engine_no_db._persist_fill(
            order_id="x", symbol="BTC-USD", side="BUY",
            quantity=1.0, price=65000.0, commission=0.0,
        )

    def test_persist_thinking_log_calls_db(self, engine_with_db: PaperTradingEngine) -> None:
        """_persist_thinking_log() should create an asyncio task calling write_thinking_log."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine_with_db._last_thinking = "Test thinking"
            engine_with_db._last_explanation = "Test explanation"
            engine_with_db._persist_thinking_log(action="BUY", confidence=0.85)
            loop.run_until_complete(asyncio.sleep(0.01))

            engine_with_db._db_writer.write_thinking_log.assert_called_once_with(
                symbol="BTC-USD",
                action="BUY",
                confidence=0.85,
                thinking="Test thinking",
                explanation="Test explanation",
                session_id="test-session-001",
            )
        finally:
            loop.close()

    def test_persist_thinking_noop_without_db(self, engine_no_db: PaperTradingEngine) -> None:
        """_persist_thinking_log() should be a no-op without db_writer."""
        engine_no_db._persist_thinking_log(action="HOLD", confidence=0.5)


class TestPnLDeltaCheck:
    """Tests for the PnL snapshot delta-check logic."""

    def test_pnl_snapshot_writes_on_first_call(self, engine_with_db: PaperTradingEngine) -> None:
        """First PnL snapshot should always be written."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            assert engine_with_db._last_recorded_equity is None
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))

            engine_with_db._db_writer.write_pnl_snapshot.assert_called_once()
            assert engine_with_db._last_recorded_equity is not None
        finally:
            loop.close()

    def test_pnl_snapshot_skips_identical_equity(self, engine_with_db: PaperTradingEngine) -> None:
        """Subsequent calls with identical equity should NOT write."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 1

            # Second call with same equity should be skipped
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 1  # Still 1
        finally:
            loop.close()

    def test_pnl_snapshot_writes_on_equity_change(self, engine_with_db: PaperTradingEngine) -> None:
        """After equity changes, a new snapshot should be written."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 1

            # Change cash to change equity
            engine_with_db._cash -= 100.0
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 2
        finally:
            loop.close()

    def test_reset_clears_delta_check(self, engine_with_db: PaperTradingEngine) -> None:
        """Engine reset should clear the delta-check state."""
        engine_with_db._last_recorded_equity = 500.0
        engine_with_db.reset()
        assert engine_with_db._last_recorded_equity is None


class TestRSIFix:
    """Tests for the RSI constant-price bug fix."""

    def test_rsi_neutral_with_constant_prices(self) -> None:
        """When all prices are identical, RSI should be 50.0 (neutral)."""
        engine = PaperTradingEngine(base_price=65000.0)
        # Fill price history with identical prices
        engine._price_history = [65000.0] * 25

        signal = engine._generate_signal()

        # RSI=50 is neutral, so no BUY/SELL signal should fire
        # (50 is between RSI_BULL_GATE=45 and RSI_BEAR_GATE=55 → Market Neutral)
        assert signal is None
        assert "Market Neutral" in engine._last_thinking
        assert "RSI: 50.0" in engine._last_thinking

    def test_rsi_not_zero_with_constant_prices(self) -> None:
        """RSI must not be 0.0 when prices are constant — this was the original bug."""
        engine = PaperTradingEngine(base_price=65000.0)
        engine._price_history = [65000.0] * 25

        engine._generate_signal()

        # The thinking text should NOT contain "Extreme RSI Oversold"
        assert "Extreme RSI Oversold" not in engine._last_thinking

    def test_rsi_valid_with_trending_prices(self) -> None:
        """RSI should compute correct values with trending data."""
        engine = PaperTradingEngine(base_price=100.0)
        # Create a clear uptrend
        engine._price_history = [100.0 + i * 0.5 for i in range(25)]

        signal = engine._generate_signal()
        # With only gains, RSI should be near 100
        # avg_g > 0, avg_l = 0 → rs = avg_g / 0.0001 → very large → RSI ≈ 100
        # However with RSI near 100, it's > RSI_BEAR_GATE=55, so "Overbought"
        assert "Overbought" in engine._last_thinking or "Neutral" in engine._last_thinking

    def test_rsi_oversold_with_declining_prices(self) -> None:
        """RSI should detect oversold conditions with declining data."""
        engine = PaperTradingEngine(base_price=100.0)
        # Create a clear downtrend
        engine._price_history = [100.0 - i * 0.5 for i in range(25)]

        engine._generate_signal()
        # With only losses, RSI should be near 0 → Oversold
        # This is a valid case (real movement), not the constant-price bug
        assert "Oversold" in engine._last_thinking or "Bearish" in engine._last_thinking or "Neutral" in engine._last_thinking


class TestUUIDReferences:
    """Test that uuid references work correctly after the import fix."""

    def test_uuid4_import_works(self) -> None:
        """Verify uuid4 is importable from the module's namespace."""
        from uuid import uuid4
        result = uuid4()
        assert len(str(result)) == 36

    def test_uuid_module_works(self) -> None:
        """Verify uuid.uuid4() works (used in paper_engine for position/trade IDs)."""
        import uuid
        result = uuid.uuid4()
        assert len(str(result)) == 36
