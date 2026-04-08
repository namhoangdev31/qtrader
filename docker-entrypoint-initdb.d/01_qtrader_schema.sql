-- ============================================================
-- QTrader TimescaleDB Schema
-- ============================================================
-- Auto-executed on first container start via docker-entrypoint-initdb.d
-- ============================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- 1. FILLS TABLE — Every executed trade fill
-- ============================================================
CREATE TABLE IF NOT EXISTS fills (
    fill_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id         VARCHAR(100) NOT NULL,
    symbol           VARCHAR(20)  NOT NULL,
    side             VARCHAR(10)  NOT NULL,          -- BUY or SELL
    quantity         NUMERIC(24, 8) NOT NULL,
    price            NUMERIC(24, 8) NOT NULL,
    commission       NUMERIC(24, 8) NOT NULL DEFAULT 0,
    notional         NUMERIC(24, 8) GENERATED ALWAYS AS (quantity * price) STORED,
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    source           VARCHAR(50)  NOT NULL DEFAULT 'qtrader',
    session_id       UUID,
    metadata         JSONB        DEFAULT '{}'
);

-- Convert to hypertable (time-partitioned)
SELECT create_hypertable('fills', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills (symbol);
CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills (order_id);
CREATE INDEX IF NOT EXISTS idx_fills_session ON fills (session_id);
CREATE INDEX IF NOT EXISTS idx_fills_timestamp ON fills (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fills_session_time ON fills (session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fills_side ON fills (side);

-- ============================================================
-- 2. ORDERS TABLE — Every submitted order
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    order_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_order_id  VARCHAR(100),
    symbol           VARCHAR(20)  NOT NULL,
    side             VARCHAR(10)  NOT NULL,          -- BUY or SELL
    order_type       VARCHAR(20)  NOT NULL DEFAULT 'MARKET',
    quantity         NUMERIC(24, 8) NOT NULL,
    price            NUMERIC(24, 8),                 -- NULL for market orders
    status           VARCHAR(20)  NOT NULL DEFAULT 'SUBMITTED',
    filled_quantity  NUMERIC(24, 8) NOT NULL DEFAULT 0,
    filled_price     NUMERIC(24, 8),
    commission       NUMERIC(24, 8) NOT NULL DEFAULT 0,
    submitted_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    filled_at        TIMESTAMPTZ,
    source           VARCHAR(50)  NOT NULL DEFAULT 'qtrader',
    session_id       UUID,
    metadata         JSONB        DEFAULT '{}'
);

SELECT create_hypertable('orders', 'submitted_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders (symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders (session_id);
CREATE INDEX IF NOT EXISTS idx_orders_submitted ON orders (submitted_at DESC);

-- ============================================================
-- 3. POSITIONS TABLE — Current position snapshots
-- ============================================================
CREATE TABLE IF NOT EXISTS positions (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20)  NOT NULL,
    quantity         NUMERIC(24, 8) NOT NULL,
    average_price    NUMERIC(24, 8) NOT NULL,
    unrealized_pnl   NUMERIC(24, 8) NOT NULL DEFAULT 0,
    realized_pnl     NUMERIC(24, 8) NOT NULL DEFAULT 0,
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    source           VARCHAR(50)  NOT NULL DEFAULT 'qtrader',
    session_id       UUID,

    -- Unique constraint: latest position per symbol
    UNIQUE (symbol, timestamp)
);

SELECT create_hypertable('positions', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions (symbol);
CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions (timestamp DESC);

-- ============================================================
-- 4. PNL_SNAPSHOTS TABLE — Periodic equity/PnL snapshots
-- ============================================================
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id               BIGSERIAL PRIMARY KEY,
    total_equity     NUMERIC(24, 8) NOT NULL,
    cash             NUMERIC(24, 8) NOT NULL,
    realized_pnl     NUMERIC(24, 8) NOT NULL DEFAULT 0,
    unrealized_pnl   NUMERIC(24, 8) NOT NULL DEFAULT 0,
    total_commission NUMERIC(24, 8) NOT NULL DEFAULT 0,
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    session_id       UUID
);

SELECT create_hypertable('pnl_snapshots', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_pnl_session ON pnl_snapshots (session_id);
CREATE INDEX IF NOT EXISTS idx_pnl_timestamp ON pnl_snapshots (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pnl_session_time ON pnl_snapshots (session_id, timestamp DESC);

-- ============================================================
-- 5. SYSTEM_EVENTS TABLE — Pipeline heartbeat, alerts, errors
-- ============================================================
CREATE TABLE IF NOT EXISTS system_events (
    id               BIGSERIAL PRIMARY KEY,
    event_type       VARCHAR(50)  NOT NULL,
    action           VARCHAR(50)  NOT NULL,
    reason           TEXT,
    source           VARCHAR(50)  NOT NULL DEFAULT 'qtrader',
    session_id       UUID,
    metadata         JSONB        DEFAULT '{}',
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('system_events', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events (event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_timestamp ON system_events (timestamp DESC);

-- ============================================================
-- 6. AI_THINKING_LOGS TABLE — Every AI decision reasoning
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_thinking_logs (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20)  NOT NULL,
    action           VARCHAR(20)  NOT NULL,
    confidence       NUMERIC(10, 4) NOT NULL,
    thinking         TEXT         NOT NULL,
    explanation      TEXT,
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    session_id       UUID,
    metadata         JSONB        DEFAULT '{}'
);

SELECT create_hypertable('ai_thinking_logs', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_thinking_symbol ON ai_thinking_logs (symbol);
CREATE INDEX IF NOT EXISTS idx_thinking_timestamp ON ai_thinking_logs (timestamp DESC);

-- ============================================================
-- 7. View: Latest position per symbol
-- ============================================================
CREATE OR REPLACE VIEW latest_positions AS
SELECT DISTINCT ON (symbol)
    symbol, quantity, average_price, unrealized_pnl, realized_pnl, timestamp
FROM positions
ORDER BY symbol, timestamp DESC;

-- ============================================================
-- 7. View: Daily PnL summary
-- ============================================================
CREATE OR REPLACE VIEW daily_pnl AS
SELECT
    DATE(timestamp) AS trade_date,
    symbol,
    COUNT(*) AS fill_count,
    SUM(CASE WHEN side = 'BUY' THEN quantity * price ELSE 0 END) AS total_bought,
    SUM(CASE WHEN side = 'SELL' THEN quantity * price ELSE 0 END) AS total_sold,
    SUM(commission) AS total_commission,
    SUM(CASE WHEN side = 'SELL' THEN quantity * price ELSE -quantity * price END) AS net_flow
FROM fills
GROUP BY DATE(timestamp), symbol
ORDER BY trade_date DESC;

-- ============================================================
-- 8. Continuous Aggregates (TimescaleDB)
-- ============================================================

-- Hourly fill volume
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_fill_volume
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    symbol,
    COUNT(*) AS fill_count,
    SUM(quantity) AS total_volume,
    SUM(quantity * price) AS total_notional,
    AVG(price) AS avg_price
FROM fills
GROUP BY bucket, symbol
WITH NO DATA;

-- Start continuous aggregation
SELECT add_continuous_aggregate_policy('hourly_fill_volume',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ============================================================
-- 9. Initial seed: $1000 starting capital snapshot
-- ============================================================
INSERT INTO pnl_snapshots (total_equity, cash, realized_pnl, unrealized_pnl, total_commission)
VALUES (1000.0, 1000.0, 0.0, 0.0, 0.0);

-- ============================================================
-- Done
-- ============================================================
COMMENT ON TABLE fills IS 'Every executed trade fill with price, quantity, commission';
COMMENT ON TABLE orders IS 'Every submitted order with lifecycle status';
COMMENT ON TABLE positions IS 'Position snapshots over time (time-series)';
COMMENT ON TABLE pnl_snapshots IS 'Periodic equity and PnL snapshots';
COMMENT ON TABLE system_events IS 'Pipeline heartbeats, alerts, and system events';
