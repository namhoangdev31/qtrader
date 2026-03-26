import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from qtrader.audit.compliance_exporter import ComplianceExporter
from qtrader.core.events import EventType


@pytest.mark.asyncio
async def test_compliance_export_csv_generation() -> None:
    """Verify that the compliance exporter produces a valid CSV file with correct columns."""
    bus = AsyncMock()
    # Mocking AuditStore and SQL result
    store = MagicMock()
    data = pl.DataFrame({
        "trace_id": [str(uuid.uuid4())],
        "model": ["XGB1"],
        "decision": ["BUY"],
        "signal": [0.85],
        "symbol": ["BTC"],
        "qty": [1.0],
        "px": [50000.0],
        "fee": [50.0],
        "pnl": [500.0]
    })
    store.query_olap.return_value = data
    
    exporter = ComplianceExporter(store, bus)
    
    # 1. Trigger export
    start_ts, end_ts = 1000, 2000
    filepath = await exporter.generate_report(start_ts, end_ts, format="csv")
    
    # 2. Assertions
    assert os.path.exists(filepath) # noqa: S101
    assert filepath.endswith(".csv") # noqa: S101
    
    # Cleanup
    if os.path.exists(filepath):
        os.remove(filepath)


@pytest.mark.asyncio
async def test_compliance_export_formats() -> None:
    """Verify that multiple export formats (JSON, Parquet) are supported correctly."""
    bus = AsyncMock()
    store = MagicMock()
    data = pl.DataFrame({"test": [1, 2, 3]})
    store.query_olap.return_value = data
    exporter = ComplianceExporter(store, bus)
    
    # Test JSON
    json_path = await exporter.generate_report(1, 10, format="json")
    assert os.path.exists(json_path) # noqa: S101
    os.remove(json_path)
    
    # Test Parquet
    pq_path = await exporter.generate_report(1, 10, format="parquet")
    assert os.path.exists(pq_path) # noqa: S101
    os.remove(pq_path)
    
    # Test Unsupported
    with pytest.raises(ValueError, match="Unsupported compliance format"):
        await exporter.generate_report(1, 10, format="txt")


@pytest.mark.asyncio
async def test_compliance_export_empty_data() -> None:
    """Verify that the exporter returns early if no matching events are found."""
    bus = AsyncMock()
    store = MagicMock()
    store.query_olap.return_value = pl.DataFrame() # Empty result
    
    exporter = ComplianceExporter(store, bus)
    filepath = await exporter.generate_report(1, 100)
    
    assert filepath == "" # noqa: S101
    assert not bus.publish.called # noqa: S101


@pytest.mark.asyncio
async def test_compliance_export_critical_failure() -> None:
    """Verify that failures are logged and ComplianceErrorEvent is emitted."""
    bus = AsyncMock()
    store = MagicMock()
    store.query_olap.side_effect = RuntimeError("DuckDB Timeout")
    
    exporter = ComplianceExporter(store, bus)
    
    with pytest.raises(RuntimeError, match="DuckDB Timeout"):
        await exporter.generate_report(1, 100)
        
    assert bus.publish.called # noqa: S101
    event = bus.publish.call_args[0][0]
    assert event.event_type == EventType.COMPLIANCE_ERROR # noqa: S101
    assert event.payload.error_type == "EXPORT_FAILURE" # noqa: S101
