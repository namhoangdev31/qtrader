-- Analytical Audit Schema (OLAP)
-- Optimized for columnar scans and SQL-based reporting

CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY,
    trace_id UUID,
    event_type VARCHAR,
    timestamp_us BIGINT,
    source VARCHAR,
    payload_json JSON,
    ingestion_time DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indices for common TCA and compliance query patterns
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(timestamp_us DESC);
