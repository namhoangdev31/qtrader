import asyncio
import time
import uuid
from decimal import Decimal
from typing import Any

import polars as pl
import pytest

from qtrader.audit.audit_store import AuditStore
from qtrader.core.events import BaseEvent, EventType, OrderEvent, OrderPayload


@pytest.mark.asyncio
async def test_audit_ingestion_and_columnar_query():
    """Verify that an OrderEvent is correctly ingested and searchable via SQL JSON-path."""
    store = AuditStore(":memory:")
    
    trace_id = uuid.uuid4()
    order = OrderEvent(
        trace_id=trace_id,
        source="Strategy_Alpha",
        payload=OrderPayload(
            order_id="ORD_AUDIT_01",
            symbol="BTC/USD",
            action="BUY",
            quantity=2.5,
            price=60000.0
        )
    )
    
    # 1. Ingest
    success = await store.append(order)
    assert success is True
    
    # 2. Simple Count Verification
    df_count = store.query_olap("SELECT COUNT(*) AS total FROM audit_events")
    assert df_count[0, "total"] == 1
    
    # 3. Aggregation and Field Extraction (Using DuckDB JSON Extension)
    # We stored: {"payload": {"order_id": "ORD_AUDIT_01", ...}}
    query = "SELECT CAST(payload_json->'$.payload.order_id' AS VARCHAR) as ord_id FROM audit_events"
    df_results = store.query_olap(query)
    
    # DuckDB json extraction might return quoted string
    extracted_id = df_results[0, "ord_id"].strip('"')
    assert extracted_id == "ORD_AUDIT_01"


@pytest.mark.asyncio
async def test_audit_performance_and_bulk_queries():
    """Benchmark aggregation across multiple events to ensure sub-100ms OLAP performance."""
    store = AuditStore(":memory:")
    
    # Ingest 100 dummy events
    for i in range(100):
         # Creating events sequentially
         evt = OrderEvent(
            trace_id=uuid.uuid4(),
            source="Feed_X",
            payload=OrderPayload(
                order_id=f"B_ORD_{i}",
                symbol="BTC/USD",
                action="BUY",
                quantity=float(i),
                price=50000.0
            )
        )
         await store.append(evt)
    
    # Perform an aggregation query
    t0 = time.perf_counter()
    # SUM quantities across all orders
    # Need to cast JSON extract to double
    query = "SELECT SUM(CAST(payload_json->'$.payload.quantity' AS DOUBLE)) as total_qty FROM audit_events"
    df_sum = store.query_olap(query)
    latency_ms = (time.perf_counter() - t0) * 1000
    
    print(f"\nOLAP Aggregate Latency (100 rows): {latency_ms:.4f}ms")
    
    # Sum of 0..99 = 4950
    assert df_sum[0, "total_qty"] == 4950.0
    assert latency_ms < 100.0 # Target performance check


def test_audit_store_connection_integrity():
    """Check that the store correctly initializes and closes DuckDB."""
    store = AuditStore(":memory:")
    assert store._conn is not None
    store.close()
    
    res = store.query_olap("SELECT 1")
    assert res.is_empty()
