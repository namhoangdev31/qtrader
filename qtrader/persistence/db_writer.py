"""Database persistence layer for trading events.

Writes fills, orders, positions, and PnL snapshots to TimescaleDB.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from qtrader.core.db import DBClient

logger = logging.getLogger("qtrader.persistence")


class TradingJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for UUID and Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class TradeDBWriter:
    """Persists trading events to TimescaleDB."""

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if they don't exist (idempotent)."""
        if self._initialized:
            return

        queries = [
            """
            CREATE TABLE IF NOT EXISTS trading_sessions (
                session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                status           VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
                mode             VARCHAR(20)  NOT NULL DEFAULT 'paper',
                start_time       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                end_time         TIMESTAMPTZ,
                initial_capital  NUMERIC(24, 8) DEFAULT 0,
                final_capital    NUMERIC(24, 8),
                summary          JSONB        DEFAULT '{}',
                metadata         JSONB        DEFAULT '{}'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS fills (
                fill_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id         VARCHAR(100) NOT NULL,
                symbol           VARCHAR(20)  NOT NULL,
                side             VARCHAR(10)  NOT NULL,
                quantity         NUMERIC(24, 8) NOT NULL,
                price            NUMERIC(24, 8) NOT NULL,
                commission       NUMERIC(24, 8) NOT NULL DEFAULT 0,
                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                source           VARCHAR(50)  NOT NULL DEFAULT 'qtrader',
                session_id       UUID REFERENCES trading_sessions(session_id),
                metadata         JSONB        DEFAULT '{}'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_order_id  VARCHAR(100),
                symbol           VARCHAR(20)  NOT NULL,
                side             VARCHAR(10)  NOT NULL,
                order_type       VARCHAR(20)  NOT NULL DEFAULT 'MARKET',
                quantity         NUMERIC(24, 8) NOT NULL,
                price            NUMERIC(24, 8),
                status           VARCHAR(20)  NOT NULL DEFAULT 'SUBMITTED',
                submitted_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                source           VARCHAR(50)  NOT NULL DEFAULT 'qtrader',
                session_id       UUID REFERENCES trading_sessions(session_id),
                metadata         JSONB        DEFAULT '{}'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS positions (
                id               BIGSERIAL PRIMARY KEY,
                symbol           VARCHAR(20)  NOT NULL,
                quantity         NUMERIC(24, 8) NOT NULL,
                average_price    NUMERIC(24, 8) NOT NULL,
                unrealized_pnl   NUMERIC(24, 8) NOT NULL DEFAULT 0,
                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                session_id       UUID REFERENCES trading_sessions(session_id),
                UNIQUE (symbol, timestamp)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS pnl_snapshots (
                id               BIGSERIAL PRIMARY KEY,
                total_equity     NUMERIC(24, 8) NOT NULL,
                cash             NUMERIC(24, 8) NOT NULL,
                realized_pnl     NUMERIC(24, 8) NOT NULL DEFAULT 0,
                unrealized_pnl   NUMERIC(24, 8) NOT NULL DEFAULT 0,
                total_commission NUMERIC(24, 8) NOT NULL DEFAULT 0,
                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                session_id       UUID REFERENCES trading_sessions(session_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_thinking_logs (
                id               BIGSERIAL PRIMARY KEY,
                symbol           VARCHAR(20)  NOT NULL,
                action           VARCHAR(20)  NOT NULL,
                confidence       NUMERIC(10, 4) NOT NULL,
                thinking         TEXT         NOT NULL,
                explanation      TEXT,
                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                session_id       UUID REFERENCES trading_sessions(session_id),
                metadata         JSONB        DEFAULT '{}'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS forensic_notes (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id       UUID REFERENCES trading_sessions(session_id),
                note_text        TEXT NOT NULL,
                note_type        VARCHAR(20) NOT NULL DEFAULT 'OBSERVATION',
                embedding        FLOAT[],
                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                metadata         JSONB DEFAULT '{}'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS market_data_raw (
                id               BIGSERIAL,
                symbol           VARCHAR(20)  NOT NULL,
                bid              NUMERIC(24, 8),
                ask              NUMERIC(24, 8),
                last_price       NUMERIC(24, 8),
                volume           NUMERIC(24, 8),
                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                session_id       UUID REFERENCES trading_sessions(session_id),
                PRIMARY KEY (id, timestamp)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS config_changes (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id       UUID REFERENCES trading_sessions(session_id),
                parameter        VARCHAR(100) NOT NULL,
                old_value        TEXT,
                new_value        TEXT,
                changed_by       VARCHAR(50) NOT NULL DEFAULT 'AI',
                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS system_health (
                id               BIGSERIAL,
                session_id       UUID REFERENCES trading_sessions(session_id),
                cpu_pct          NUMERIC(5, 2),
                mem_pct          NUMERIC(5, 2),
                latency_ms       INTEGER,
                status           VARCHAR(50),
                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (id, timestamp)
            );
            """,
        ]

        for query in queries:
            try:
                await DBClient.execute(query)
            except Exception as e:
                logger.warning(f"[DB] Table creation skipped/failed: {e}")

        # Try to create hypertables (requires timescaledb extension)
        hypertable_queries = [
            "SELECT create_hypertable('fills', 'timestamp', if_not_exists => TRUE);",
            "SELECT create_hypertable('orders', 'submitted_at', if_not_exists => TRUE);",
            "SELECT create_hypertable('positions', 'timestamp', if_not_exists => TRUE);",
            "SELECT create_hypertable('pnl_snapshots', 'timestamp', if_not_exists => TRUE);",
            "SELECT create_hypertable('ai_thinking_logs', 'timestamp', if_not_exists => TRUE);",
            "SELECT create_hypertable('market_data_raw', 'timestamp', if_not_exists => TRUE);",
            "SELECT create_hypertable('system_health', 'timestamp', if_not_exists => TRUE);",
        ]
        for query in hypertable_queries:
            try:
                await DBClient.execute(query)
            except Exception as e:
                logger.debug(f"[DB] Hypertable creation skipped: {e}")

        self._initialized = True
        await self.cleanup_stale_sessions()
        logger.info("[DB] Persistence layer initialized (Session-Centric)")

    async def purge_database(self) -> None:
        """NUCLEAR RESET: Drop all tables and re-initialize."""
        tables = [
            "system_health", "config_changes", "market_data_raw", 
            "forensic_notes", "ai_thinking_logs", "pnl_snapshots", 
            "positions", "fills", "orders", "trading_sessions"
        ]
        for table in tables:
            try:
                await DBClient.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                logger.warning(f"[DB] Purged table: {table}")
            except Exception as e:
                logger.error(f"[DB] Failed to purge table {table}: {e}")

        self._initialized = False
        await self.initialize()
        logger.info("[DB] Database fully reconstructed.")

    async def cleanup_stale_sessions(self) -> None:
        """Mark all orphaned 'ACTIVE' sessions as 'ABORTED' on startup."""
        query = """
            UPDATE trading_sessions
            SET status = 'ABORTED', end_time = NOW()
            WHERE status = 'ACTIVE'
        """
        try:
            res = await DBClient.execute(query)
            # res is usually a string like "UPDATE 1"
            count = res.split(" ")[-1] if res else "0"
            if count != "0":
                logger.warning(f"[DB] Cleaned up {count} stale 'ACTIVE' sessions.")
        except Exception as e:
            logger.error(f"[DB] Stale session cleanup failed: {e}")

    async def write_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        source: str = "qtrader",
        session_id: str | None = None,
    ) -> None:
        """Persist a fill to the database."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO fills (
                order_id, symbol, side, quantity, price, 
                commission, source, session_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        try:
            await DBClient.execute(
                query,
                order_id,
                symbol,
                side,
                str(quantity),
                str(price),
                str(commission),
                source,
                session_id,
            )
            logger.info(
                f"[DB] Fill persisted: {symbol} {side} {quantity}@{price} "
                f"(Session: {session_id})"
            )
        except Exception as e:
            logger.error(f"[DB] Failed to persist fill: {e}")

    async def write_order(
        self,
        broker_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        source: str = "qtrader",
        session_id: str | None = None,
    ) -> None:
        """Persist an order to the database."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO orders (
                broker_order_id, symbol, side, order_type, 
                quantity, price, source, session_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        try:
            await DBClient.execute(
                query,
                broker_order_id,
                symbol,
                side,
                order_type,
                str(quantity),
                str(price) if price else None,
                source,
                session_id,
            )
            logger.info(
                f"[DB] Order persisted: {symbol} {side} {quantity} "
                f"(Session: {session_id})"
            )
        except Exception as e:
            logger.error(f"[DB] Failed to persist order: {e}")

    async def write_position(
        self,
        symbol: str,
        quantity: Decimal,
        average_price: Decimal,
        unrealized_pnl: Decimal = Decimal("0"),
        session_id: str | None = None,
    ) -> None:
        """Persist a position snapshot to the database."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO positions (symbol, quantity, average_price, unrealized_pnl, session_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (symbol, timestamp) DO UPDATE
            SET quantity = EXCLUDED.quantity, 
                average_price = EXCLUDED.average_price, 
                unrealized_pnl = EXCLUDED.unrealized_pnl
        """
        try:
            await DBClient.execute(
                query, symbol, str(quantity), str(average_price), str(unrealized_pnl), session_id
            )
        except Exception as e:
            logger.error(f"[DB] Failed to persist position: {e}")

    async def write_pnl_snapshot(
        self,
        total_equity: Decimal,
        cash: Decimal,
        realized_pnl: Decimal = Decimal("0"),
        unrealized_pnl: Decimal = Decimal("0"),
        total_commission: Decimal = Decimal("0"),
        session_id: str | None = None,
    ) -> None:
        """Persist a PnL snapshot to the database."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO pnl_snapshots (
                total_equity, cash, realized_pnl, 
                unrealized_pnl, total_commission, session_id
            )
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        try:
            await DBClient.execute(
                query,
                str(total_equity),
                str(cash),
                str(realized_pnl),
                str(unrealized_pnl),
                str(total_commission),
                session_id,
            )
        except Exception as e:
            logger.error(f"[DB] Failed to persist PnL snapshot: {e}")

    async def get_latest_positions(self) -> list[dict[str, Any]]:
        """Get latest position per symbol."""
        query = """
            SELECT DISTINCT ON (symbol) symbol, quantity, average_price, unrealized_pnl, timestamp
            FROM positions ORDER BY symbol, timestamp DESC
        """
        try:
            rows = await DBClient.fetch(query)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch positions: {e}")
            return []

    async def get_recent_fills(self, limit: int = 50, session_id: str | None = None) -> list[dict[str, Any]]:
        """Get recent fills."""
        if session_id:
            query = """
                SELECT fill_id, order_id, symbol, side, quantity, price, commission, timestamp
                FROM fills WHERE session_id = $2 ORDER BY timestamp DESC LIMIT $1
            """
            params = [limit, session_id]
        else:
            query = """
                SELECT fill_id, order_id, symbol, side, quantity, price, commission, timestamp
                FROM fills ORDER BY timestamp DESC LIMIT $1
            """
            params = [limit]

        try:
            rows = await DBClient.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch fills: {e}")
            return []

    async def get_pnl_history(self, limit: int = 100, session_id: str | None = None) -> list[dict[str, Any]]:
        """Get recent PnL snapshots."""
        if session_id:
            query = """
                SELECT total_equity, cash, realized_pnl, unrealized_pnl, total_commission, timestamp
                FROM pnl_snapshots WHERE session_id = $2 ORDER BY timestamp DESC LIMIT $1
            """
            params = [limit, session_id]
        else:
            query = """
                SELECT total_equity, cash, realized_pnl, unrealized_pnl, total_commission, timestamp
                FROM pnl_snapshots ORDER BY timestamp DESC LIMIT $1
            """
            params = [limit]

        try:
            rows = await DBClient.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch PnL history: {e}")
            return []

    async def write_thinking_log(
        self,
        symbol: str,
        action: str,
        confidence: float,
        thinking: str,
        explanation: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> None:
        """Persist an AI thinking log."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO ai_thinking_logs (
                symbol, action, confidence, thinking, 
                explanation, metadata, session_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        try:
            await DBClient.execute(
                query,
                symbol,
                action,
                confidence,
                thinking,
                explanation,
                json.dumps(metadata or {}, cls=TradingJSONEncoder),
                session_id,
            )
        except Exception as e:
            logger.error(f"[DB] Failed to persist thinking log: {e}")

    async def get_recent_thinking_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent AI thinking logs."""
        query = """
            SELECT symbol, action, confidence, thinking, explanation, timestamp
            FROM ai_thinking_logs ORDER BY timestamp DESC LIMIT $1
        """
        try:
            rows = await DBClient.fetch(query, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch thinking logs: {e}")
            return []

    async def start_session(
        self, initial_capital: Decimal, metadata: dict[str, Any] | None = None
    ) -> str:
        """Start a new trading session with initial capital."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO trading_sessions (initial_capital, metadata)
            VALUES ($1, $2)
            RETURNING session_id
        """
        try:
            row = await DBClient.fetchrow(
                query, str(initial_capital), json.dumps(metadata or {}, cls=TradingJSONEncoder)
            )
            session_id = str(row["session_id"])
            logger.info(f"[DB] Session started: {session_id} | Capital: {initial_capital}")
            return session_id
        except Exception as e:
            logger.error(f"[DB] Failed to start session: {e}")
            raise

    async def stop_session(
        self, session_id: str, final_capital: Decimal, summary: dict[str, Any]
    ) -> None:
        """Stop an active trading session and store final capital + summary."""
        query = """
            UPDATE trading_sessions
            SET status = 'COMPLETED', end_time = NOW(), final_capital = $2, summary = $3
            WHERE session_id = $1
        """
        try:
            await DBClient.execute(
                query, session_id, str(final_capital), json.dumps(summary, cls=TradingJSONEncoder)
            )
            logger.info(f"[DB] Session stopped: {session_id} | Final Capital: {final_capital}")
        except Exception as e:
            logger.error(f"[DB] Failed to stop session: {e}")

    async def get_active_session(self) -> dict[str, Any] | None:
        """Get the currently active trading session if any."""
        query = """
            SELECT session_id, status, start_time, metadata
            FROM trading_sessions
            WHERE status = 'ACTIVE'
            ORDER BY start_time DESC
            LIMIT 1
        """
        try:
            row = await DBClient.fetchrow(query)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[DB] Failed to fetch active session: {e}")
            return None

    async def get_session_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent trading sessions."""
        query = """
            SELECT session_id, status, start_time, end_time, summary
            FROM trading_sessions
            ORDER BY start_time DESC
            LIMIT $1
        """
        try:
            rows = await DBClient.fetch(query, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch session history: {e}")
            return []

    async def write_forensic_note(
        self,
        content: str,
        note_type: str = "OBSERVATION",
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a forensic note and return its UUID."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO forensic_notes (session_id, note_text, note_type, metadata)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        try:
            row = await DBClient.fetchrow(
                query,
                session_id,
                content,
                note_type,
                json.dumps(metadata or {}, cls=TradingJSONEncoder),
            )
            note_id = str(row["id"])
            logger.info(f"[DB] Forensic note persisted: {note_id}")
            return note_id
        except Exception as e:
            logger.error(f"[DB] Failed to persist forensic note: {e}")
            raise

    async def update_note_embedding(self, note_id: str, embedding: list[float]) -> None:
        """Update the semantic embedding for a specific note (Async worker)."""
        query = "UPDATE forensic_notes SET embedding = $2 WHERE id = $1"
        try:
            await DBClient.execute(query, note_id, embedding)
            logger.debug(f"[DB] Updated embedding for note {note_id}")
        except Exception as e:
            logger.error(f"[DB] Failed to update note embedding {note_id}: {e}")

    async def write_raw_market_data(
        self,
        symbol: str,
        bid: Decimal | None = None,
        ask: Decimal | None = None,
        last_price: Decimal | None = None,
        volume: Decimal | None = None,
        session_id: str | None = None,
    ) -> None:
        """Persist raw market data (ticks)."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO market_data_raw (symbol, bid, ask, last_price, volume, session_id)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        try:
            await DBClient.execute(
                query, 
                symbol, 
                str(bid) if bid else None, 
                str(ask) if ask else None, 
                str(last_price) if last_price else None, 
                str(volume) if volume else None, 
                session_id
            )
        except Exception as e:
            logger.error(f"[DB] Failed to persist raw market data: {e}")

    async def write_config_change(
        self,
        session_id: str | None,
        parameter: str,
        old_value: Any,
        new_value: Any,
        changed_by: str = "AI",
    ) -> None:
        """Persist a dynamic configuration change."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO config_changes (session_id, parameter, old_value, new_value, changed_by)
            VALUES ($1, $2, $3, $4, $5)
        """
        try:
            await DBClient.execute(
                query,
                session_id,
                parameter,
                str(old_value),
                str(new_value),
                changed_by,
            )
            logger.info(f"[DB] Config change logged: {parameter} -> {new_value}")
        except Exception as e:
            logger.error(f"[DB] Failed to log config change: {e}")

    async def write_system_health(
        self,
        session_id: str | None,
        cpu_pct: float,
        mem_pct: float,
        latency_ms: int,
        status: str = "OK",
    ) -> None:
        """Persist system health metrics."""
        if not self._initialized:
            await self.initialize()

        query = """
            INSERT INTO system_health (session_id, cpu_pct, mem_pct, latency_ms, status)
            VALUES ($1, $2, $3, $4, $5)
        """
        try:
            await DBClient.execute(query, session_id, cpu_pct, mem_pct, latency_ms, status)
        except Exception as e:
            logger.error(f"[DB] Failed to persist system health: {e}")

    async def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        """Get a specific session by ID."""
        query = """
            SELECT session_id, status, start_time, end_time, summary
            FROM trading_sessions
            WHERE session_id = $1
        """
        try:
            row = await DBClient.fetchrow(query, session_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[DB] Failed to fetch session {session_id}: {e}")
            return None
