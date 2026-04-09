from __future__ import annotations
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from uuid import uuid4
import pytest
from qtrader.execution.paper_engine import PaperTradingEngine


@pytest.fixture
def mock_db_writer() -> AsyncMock:
    writer = AsyncMock()
    writer.write_fill = AsyncMock()
    writer.write_thinking_log = AsyncMock()
    writer.write_pnl_snapshot = AsyncMock()
    return writer


@pytest.fixture
def engine_with_db(mock_db_writer: AsyncMock) -> PaperTradingEngine:
    engine = PaperTradingEngine(
        starting_capital=1000.0,
        base_price=65000.0,
        db_writer=mock_db_writer,
        session_id="test-session-001",
    )
    return engine


@pytest.fixture
def engine_no_db() -> PaperTradingEngine:
    return PaperTradingEngine(starting_capital=1000.0, base_price=65000.0)


class TestPaperEngineDBBridge:
    def test_set_db_writer_injects_correctly(
        self, engine_no_db: PaperTradingEngine, mock_db_writer: AsyncMock
    ) -> None:
        assert engine_no_db._db_writer is None
        assert engine_no_db._session_id is None
        engine_no_db.set_db_writer(mock_db_writer, "inject-session-002")
        assert engine_no_db._db_writer is mock_db_writer
        assert engine_no_db._session_id == "inject-session-002"

    def test_persist_fill_calls_write_fill(self, engine_with_db: PaperTradingEngine) -> None:
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
        engine_no_db._persist_fill(
            order_id="x", symbol="BTC-USD", side="BUY", quantity=1.0, price=65000.0, commission=0.0
        )

    def test_persist_thinking_log_calls_db(self, engine_with_db: PaperTradingEngine) -> None:
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
        engine_no_db._persist_thinking_log(action="HOLD", confidence=0.5)


class TestPnLDeltaCheck:
    def test_pnl_snapshot_writes_on_first_call(self, engine_with_db: PaperTradingEngine) -> None:
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 1
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 1
        finally:
            loop.close()

    def test_pnl_snapshot_writes_on_equity_change(self, engine_with_db: PaperTradingEngine) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 1
            engine_with_db._cash -= 100.0
            engine_with_db._persist_pnl_snapshot()
            loop.run_until_complete(asyncio.sleep(0.01))
            assert engine_with_db._db_writer.write_pnl_snapshot.call_count == 2
        finally:
            loop.close()

    def test_reset_clears_delta_check(self, engine_with_db: PaperTradingEngine) -> None:
        engine_with_db._last_recorded_equity = 500.0
        engine_with_db.reset()
        assert engine_with_db._last_recorded_equity is None


class TestRSIFix:
    def test_rsi_neutral_with_constant_prices(self) -> None:
        engine = PaperTradingEngine(base_price=65000.0)
        engine._price_history = [65000.0] * 25
        signal = engine._generate_signal()
        assert signal is None
        assert "Market Neutral" in engine._last_thinking
        assert "RSI: 50.0" in engine._last_thinking

    def test_rsi_not_zero_with_constant_prices(self) -> None:
        engine = PaperTradingEngine(base_price=65000.0)
        engine._price_history = [65000.0] * 25
        engine._generate_signal()
        assert "Extreme RSI Oversold" not in engine._last_thinking

    def test_rsi_valid_with_trending_prices(self) -> None:
        engine = PaperTradingEngine(base_price=100.0)
        engine._price_history = [100.0 + i * 0.5 for i in range(25)]
        _ = engine._generate_signal()
        assert "Overbought" in engine._last_thinking or "Neutral" in engine._last_thinking

    def test_rsi_oversold_with_declining_prices(self) -> None:
        engine = PaperTradingEngine(base_price=100.0)
        engine._price_history = [100.0 - i * 0.5 for i in range(25)]
        engine._generate_signal()
        assert (
            "Oversold" in engine._last_thinking
            or "Bearish" in engine._last_thinking
            or "Neutral" in engine._last_thinking
        )


class TestUUIDReferences:
    def test_uuid4_import_works(self) -> None:
        result = uuid4()
        assert len(str(result)) == 36

    def test_uuid_module_works(self) -> None:
        result = uuid.uuid4()
        assert len(str(result)) == 36
