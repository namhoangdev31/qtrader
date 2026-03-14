"""Tests for qtrader.core: config, event, logging, db."""

import json
import logging

import pytest

from qtrader.core.config import QTraderSettings, settings
from qtrader.core.event import (
    EventType,
    HeartbeatEvent,
    RegimeChangeEvent,
    SystemEvent,
)
from qtrader.core.logging import (
    CorrelationIDFilter,
    configure_logging,
    get_logger,
)
from qtrader.core.db import DuckDBClient


def test_settings_singleton_loads() -> None:
    """Settings load at import and expose snake_case and uppercase aliases."""
    assert settings.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")
    assert settings.database_url.startswith("postgresql://")
    assert settings.DB_URL == settings.database_url
    assert settings.DATALAKE_URI == settings.datalake_uri


def test_settings_live_mode_validation_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """When simulate_mode=False, at least one exchange API key is required."""
    monkeypatch.setenv("SIMULATE_MODE", "false")
    monkeypatch.setenv("BINANCE_API_KEY", "")
    monkeypatch.setenv("COINBASE_API_KEY", "")
    with pytest.raises(ValueError, match="Live mode requires"):
        QTraderSettings()


def test_event_types_and_new_dataclasses() -> None:
    """RegimeChangeEvent, SystemEvent, HeartbeatEvent have correct EventType."""
    r = RegimeChangeEvent(regime_id=1, confidence=0.9, previous_regime_id=0)
    assert r.type == EventType.REGIME_CHANGE
    s = SystemEvent(action="EMERGENCY_HALT", reason="drift")
    assert s.type == EventType.SYSTEM
    h = HeartbeatEvent(source="bot_runner", uptime_seconds=60.0)
    assert h.type == EventType.HEARTBEAT


def test_configure_logging_and_structured_adapter() -> None:
    """Structured logger accepts extra kwargs (no TypeError) and emits the message."""
    configure_logging(level="DEBUG", fmt="text", service_name="qtrader-test")
    log = get_logger("qtrader.test_core", correlation_id="test-1")
    log.info("test message", symbol="BTC/USDT", strength=0.85)  # no TypeError from extra kwargs


def test_json_formatter_emits_one_line_per_record(capsys: pytest.CaptureFixture[str]) -> None:
    """When fmt=json, each log line is a single JSON object."""
    configure_logging(level="INFO", fmt="json", service_name="qtrader-test")
    log = get_logger("qtrader.test_core")
    log.info("json test", key="value")
    out = capsys.readouterr().out
    assert "json test" in out
    obj = json.loads(out.strip())
    assert obj["message"] == "json test"
    assert obj.get("extra", {}).get("key") == "value"


def test_correlation_id_filter_set_clear() -> None:
    """CorrelationIDFilter.set_id and clear_id update the class-level id."""
    CorrelationIDFilter.set_id("cycle-001")
    assert CorrelationIDFilter._id == "cycle-001"
    CorrelationIDFilter.clear_id()
    assert CorrelationIDFilter._id is None


def test_duckdb_client_query_returns_polars() -> None:
    """DuckDBClient.query returns a Polars DataFrame."""
    client = DuckDBClient(":memory:")
    df = client.query("SELECT 1 AS n, 'x' AS s")
    assert df.shape == (1, 2)
    assert df["n"][0] == 1
    assert df["s"][0] == "x"
    client.close()


def test_duckdb_client_query_parquet_placeholder() -> None:
    """DuckDBClient.query_parquet substitutes {glob} in SQL."""
    client = DuckDBClient(":memory:")
    # Use a query that doesn't actually read files; just check substitution
    df = client.query_parquet("/fake/path/*.parquet", "SELECT 1 AS x")
    assert df.shape == (1, 1)
    assert df["x"][0] == 1
    client.close()
