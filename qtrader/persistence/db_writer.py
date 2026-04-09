from __future__ import annotations
import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID
from qtrader.core.db import DBClient

logger = logging.getLogger("qtrader.persistence")


class TradingJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class TradeDBWriter:
    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        queries = [
            "\n            CREATE TABLE IF NOT EXISTS trading_sessions (\n                session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n                status           TEXT NOT NULL DEFAULT 'ACTIVE',\n                mode             TEXT NOT NULL DEFAULT 'paper',\n                start_time       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n                end_time         TIMESTAMPTZ,\n                initial_capital  NUMERIC(24, 8) DEFAULT 0,\n                final_capital    NUMERIC(24, 8),\n                summary          JSONB        DEFAULT '{}',\n                metadata         JSONB        DEFAULT '{}'\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS fills (\n                fill_id          UUID DEFAULT gen_random_uuid(),\n                order_id         TEXT NOT NULL,\n                symbol           TEXT NOT NULL,\n                side             TEXT NOT NULL,\n                quantity         NUMERIC(24, 8) NOT NULL,\n                price            NUMERIC(24, 8) NOT NULL,\n                commission       NUMERIC(24, 8) NOT NULL DEFAULT 0,\n                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n                source           TEXT NOT NULL DEFAULT 'qtrader',\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                metadata         JSONB DEFAULT '{}',\n                PRIMARY KEY (fill_id, timestamp)\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS orders (\n                order_id         UUID DEFAULT gen_random_uuid(),\n                broker_order_id  TEXT,\n                symbol           TEXT NOT NULL,\n                side             TEXT NOT NULL,\n                order_type       TEXT NOT NULL DEFAULT 'MARKET',\n                quantity         NUMERIC(24, 8) NOT NULL,\n                price            NUMERIC(24, 8),\n                status           TEXT NOT NULL DEFAULT 'SUBMITTED',\n                submitted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n                source           TEXT NOT NULL DEFAULT 'qtrader',\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                metadata         JSONB DEFAULT '{}',\n                PRIMARY KEY (order_id, submitted_at)\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS positions (\n                id               BIGSERIAL,\n                symbol           TEXT NOT NULL,\n                quantity         NUMERIC(24, 8) NOT NULL,\n                average_price    NUMERIC(24, 8) NOT NULL,\n                unrealized_pnl   NUMERIC(24, 8) NOT NULL DEFAULT 0,\n                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                PRIMARY KEY (id, timestamp),\n                UNIQUE (symbol, timestamp)\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS pnl_snapshots (\n                id               BIGSERIAL,\n                total_equity     NUMERIC(24, 8) NOT NULL,\n                cash             NUMERIC(24, 8) NOT NULL,\n                realized_pnl     NUMERIC(24, 8) NOT NULL DEFAULT 0,\n                unrealized_pnl   NUMERIC(24, 8) NOT NULL DEFAULT 0,\n                total_commission NUMERIC(24, 8) NOT NULL DEFAULT 0,\n                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                PRIMARY KEY (id, timestamp)\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS ai_thinking_logs (\n                id               BIGSERIAL,\n                symbol           TEXT NOT NULL,\n                action           TEXT NOT NULL,\n                confidence       NUMERIC(10, 4) NOT NULL,\n                thinking         TEXT NOT NULL,\n                explanation      TEXT,\n                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                metadata         JSONB        DEFAULT '{}',\n                PRIMARY KEY (id, timestamp)\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS forensic_notes (\n                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                note_text        TEXT NOT NULL,\n                note_type        TEXT NOT NULL DEFAULT 'OBSERVATION',\n                embedding        FLOAT[],\n                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n                metadata         JSONB DEFAULT '{}'\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS market_data_raw (\n                id               BIGSERIAL,\n                symbol           TEXT NOT NULL,\n                bid              NUMERIC(24, 8),\n                ask              NUMERIC(24, 8),\n                last_price       NUMERIC(24, 8),\n                volume           NUMERIC(24, 8),\n                timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                PRIMARY KEY (id, timestamp)\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS config_changes (\n                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                parameter        TEXT NOT NULL,\n                old_value        TEXT,\n                new_value        TEXT,\n                changed_by       TEXT NOT NULL DEFAULT 'AI',\n                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW()\n            );\n            ",
            "\n            CREATE TABLE IF NOT EXISTS system_health (\n                id               BIGSERIAL,\n                session_id       UUID REFERENCES trading_sessions(session_id),\n                cpu_pct          NUMERIC(5, 2),\n                mem_pct          NUMERIC(5, 2),\n                latency_ms       INTEGER,\n                status           TEXT,\n                timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n                PRIMARY KEY (id, timestamp)\n            );\n            ",
        ]
        for query in queries:
            try:
                await DBClient.execute(query)
            except Exception as e:
                logger.warning(f"[DB] Table creation skipped/failed: {e}")
        hypertable_queries = [
            "SELECT create_hypertable('fills', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('orders', 'submitted_at', if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('positions', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('pnl_snapshots', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('ai_thinking_logs', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('market_data_raw', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('system_health', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
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
        tables = [
            "system_health",
            "config_changes",
            "market_data_raw",
            "forensic_notes",
            "ai_thinking_logs",
            "pnl_snapshots",
            "positions",
            "fills",
            "orders",
            "trading_sessions",
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
        query = "\n            UPDATE trading_sessions\n            SET status = 'ABORTED', end_time = NOW()\n            WHERE status = 'ACTIVE'\n        "
        try:
            res = await DBClient.execute(query)
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO fills (\n                order_id, symbol, side, quantity, price,\n                commission, source, session_id\n            )\n            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)\n        "
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
                f"[DB] Fill persisted: {symbol} {side} {quantity}@{price} (Session: {session_id})"
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO orders (\n                broker_order_id, symbol, side, order_type,\n                quantity, price, source, session_id\n            )\n            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)\n        "
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
            logger.info(f"[DB] Order persisted: {symbol} {side} {quantity} (Session: {session_id})")
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO positions (symbol, quantity, average_price, unrealized_pnl, session_id)\n            VALUES ($1, $2, $3, $4, $5)\n            ON CONFLICT (symbol, timestamp) DO UPDATE\n            SET quantity = EXCLUDED.quantity,\n                average_price = EXCLUDED.average_price,\n                unrealized_pnl = EXCLUDED.unrealized_pnl\n        "
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO pnl_snapshots (\n                total_equity, cash, realized_pnl,\n                unrealized_pnl, total_commission, session_id\n            )\n            VALUES ($1, $2, $3, $4, $5, $6)\n        "
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
        query = "\n            SELECT DISTINCT ON (symbol) symbol, quantity, average_price, unrealized_pnl, timestamp\n            FROM positions ORDER BY symbol, timestamp DESC\n        "
        try:
            rows = await DBClient.fetch(query)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch positions: {e}")
            return []

    async def get_recent_fills(
        self, limit: int = 50, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        if session_id:
            query = "\n                SELECT fill_id, order_id, symbol, side, quantity, price, commission, timestamp\n                FROM fills WHERE session_id = $2 ORDER BY timestamp DESC LIMIT $1\n            "
            params = [limit, session_id]
        else:
            query = "\n                SELECT fill_id, order_id, symbol, side, quantity, price, commission, timestamp\n                FROM fills ORDER BY timestamp DESC LIMIT $1\n            "
            params = [limit]
        try:
            rows = await DBClient.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch fills: {e}")
            return []

    async def get_pnl_history(
        self, limit: int = 100, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        if session_id:
            query = "\n                SELECT total_equity, cash, realized_pnl, unrealized_pnl, total_commission, timestamp\n                FROM pnl_snapshots WHERE session_id = $2 ORDER BY timestamp DESC LIMIT $1\n            "
            params = [limit, session_id]
        else:
            query = "\n                SELECT total_equity, cash, realized_pnl, unrealized_pnl, total_commission, timestamp\n                FROM pnl_snapshots ORDER BY timestamp DESC LIMIT $1\n            "
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO ai_thinking_logs (\n                symbol, action, confidence, thinking,\n                explanation, metadata, session_id\n            )\n            VALUES ($1, $2, $3, $4, $5, $6, $7)\n        "
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
        query = "\n            SELECT symbol, action, confidence, thinking, explanation, timestamp\n            FROM ai_thinking_logs ORDER BY timestamp DESC LIMIT $1\n        "
        try:
            rows = await DBClient.fetch(query, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[DB] Failed to fetch thinking logs: {e}")
            return []

    async def start_session(
        self, initial_capital: Decimal, metadata: dict[str, Any] | None = None
    ) -> str:
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO trading_sessions (initial_capital, metadata)\n            VALUES ($1, $2)\n            RETURNING session_id\n        "
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
        query = "\n            UPDATE trading_sessions\n            SET status = 'COMPLETED', end_time = NOW(), final_capital = $2, summary = $3\n            WHERE session_id = $1\n        "
        try:
            await DBClient.execute(
                query, session_id, str(final_capital), json.dumps(summary, cls=TradingJSONEncoder)
            )
            logger.info(f"[DB] Session stopped: {session_id} | Final Capital: {final_capital}")
        except Exception as e:
            logger.error(f"[DB] Failed to stop session: {e}")

    async def get_active_session(self) -> dict[str, Any] | None:
        query = "\n            SELECT session_id, status, start_time, metadata\n            FROM trading_sessions\n            WHERE status = 'ACTIVE'\n            ORDER BY start_time DESC\n            LIMIT 1\n        "
        try:
            row = await DBClient.fetchrow(query)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[DB] Failed to fetch active session: {e}")
            return None

    async def get_session_history(self, limit: int = 10) -> list[dict[str, Any]]:
        query = "\n            SELECT session_id, status, start_time, end_time, summary\n            FROM trading_sessions\n            ORDER BY start_time DESC\n            LIMIT $1\n        "
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO forensic_notes (session_id, note_text, note_type, metadata)\n            VALUES ($1, $2, $3, $4)\n            RETURNING id\n        "
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO market_data_raw (symbol, bid, ask, last_price, volume, session_id)\n            VALUES ($1, $2, $3, $4, $5, $6)\n        "
        try:
            await DBClient.execute(
                query,
                symbol,
                str(bid) if bid else None,
                str(ask) if ask else None,
                str(last_price) if last_price else None,
                str(volume) if volume else None,
                session_id,
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO config_changes (session_id, parameter, old_value, new_value, changed_by)\n            VALUES ($1, $2, $3, $4, $5)\n        "
        try:
            await DBClient.execute(
                query, session_id, parameter, str(old_value), str(new_value), changed_by
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
        if not self._initialized:
            await self.initialize()
        query = "\n            INSERT INTO system_health (session_id, cpu_pct, mem_pct, latency_ms, status)\n            VALUES ($1, $2, $3, $4, $5)\n        "
        try:
            await DBClient.execute(query, session_id, cpu_pct, mem_pct, latency_ms, status)
        except Exception as e:
            logger.error(f"[DB] Failed to persist system health: {e}")

    async def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        query = "\n            SELECT session_id, status, start_time, end_time, summary\n            FROM trading_sessions\n            WHERE session_id = $1\n        "
        try:
            row = await DBClient.fetchrow(query, session_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[DB] Failed to fetch session {session_id}: {e}")
            return None
