from unittest.mock import AsyncMock, patch

import pytest

from qtrader.data.lineage import LineageStore


@pytest.mark.asyncio
async def test_initialize_lineage() -> None:
    """Verify that initialize creates the tables."""
    store = LineageStore()
    with patch("qtrader.core.db.DBClient.execute", new_callable=AsyncMock) as mock_execute:
        await store.initialize()
        assert mock_execute.called


@pytest.mark.asyncio
async def test_record_feature_lineage() -> None:
    """Verify that feature lineage is recorded correctly."""
    store = LineageStore()

    with patch("qtrader.core.db.DBClient.execute", new_callable=AsyncMock) as mock_execute:
        await store.record_feature("rsi_14", ["close"], "ds_001")
        assert mock_execute.called
        # Check if query arguments are passed correctly
        args = mock_execute.call_args[0]
        assert args[1] == "rsi_14"
        assert "close" in args[2]  # JSON dumped string
        assert args[3] == "ds_001"


@pytest.mark.asyncio
async def test_get_feature_lineage() -> None:
    """Verify that feature lineage can be retrieved and parsed."""
    store = LineageStore()

    mock_row = {
        "feature_name": "rsi_14",
        "source_columns": '["close"]',
        "dataset_id": "ds_001",
        "created_at": "2025-01-01 00:00:00",
    }

    with patch("qtrader.core.db.DBClient.fetchrow", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_row
        result = await store.get_feature_lineage("rsi_14")

        assert result is not None
        assert result["feature_name"] == "rsi_14"
        assert result["source_columns"] == ["close"]
        assert result["dataset_id"] == "ds_001"


@pytest.mark.asyncio
async def test_get_nonexistent_feature() -> None:
    """Retrieving a non-existent feature should return None."""
    store = LineageStore()

    with patch("qtrader.core.db.DBClient.fetchrow", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        result = await store.get_feature_lineage("unknown")
        assert result is None
