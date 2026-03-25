from unittest.mock import AsyncMock, patch

import polars as pl
import pytest

from qtrader.data.versioning import VersionManager

# ──────────────────────────────────────────────
# Constants (PLR2004, N806)
# ──────────────────────────────────────────────
EXPECTED_ROW_COUNT = 100
MANAGER_RAW_COUNT = 3


@pytest.mark.asyncio
async def test_initialize_versioning() -> None:
    """Verify that initialize creates the tables."""
    manager = VersionManager()
    with patch("qtrader.core.db.DBClient.execute", new_callable=AsyncMock) as mock_execute:
        await manager.initialize()
        assert mock_execute.called


@pytest.mark.asyncio
async def test_create_version() -> None:
    """Verify that dataset versions are created with correct hashes."""
    manager = VersionManager()

    df = pl.DataFrame({"close": [10.5, 11.2, 10.8]})
    config = {"symbol": "BTCUSDT", "timeframe": "1h"}

    with patch("qtrader.core.db.DBClient.execute", new_callable=AsyncMock) as mock_execute:
        version = await manager.create_version("ds_001", df, config)

        assert version is not None
        assert "_" in version  # Format: timestamp_hash
        assert mock_execute.called

        args = mock_execute.call_args[0]
        assert args[1] == "ds_001"
        assert args[2] == version
        assert "BTCUSDT" in args[3]  # JSON config
        assert args[4] == MANAGER_RAW_COUNT


@pytest.mark.asyncio
async def test_get_version_metadata() -> None:
    """Verify that version metadata can be retrieved and parsed."""
    manager = VersionManager()

    mock_row = {
        "dataset_id": "ds_001",
        "version": "20250101_abcdefg",
        "config": '{"symbol": "BTCUSDT"}',
        "row_count": EXPECTED_ROW_COUNT,
        "hash": "somehash",
        "created_at": "2025-01-01 00:00:00",
    }

    with patch("qtrader.core.db.DBClient.fetchrow", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_row
        result = await manager.get_version_metadata("ds_001")

        assert result is not None
        assert result["dataset_id"] == "ds_001"
        assert result["config"] == {"symbol": "BTCUSDT"}
        assert result["row_count"] == EXPECTED_ROW_COUNT


@pytest.mark.asyncio
async def test_get_nonexistent_version() -> None:
    """Retrieving metadata for an unknown dataset should return None."""
    manager = VersionManager()

    with patch("qtrader.core.db.DBClient.fetchrow", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        result = await manager.get_version_metadata("unknown")
        assert result is None
