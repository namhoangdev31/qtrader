import hashlib
import json
import logging
from datetime import datetime
from typing import Any

import polars as pl

from qtrader.core.db import DBClient

_LOG = logging.getLogger(__name__)


class VersionManager:
    """
    Manages dataset versions by snapshotting metadata and hashes.
    Ensures that any dataset used for model training is reproducible.
    """

    async def initialize(self) -> None:
        """Create dataset lineage table if it doesn't exist."""
        dataset_lineage_query = """
        CREATE TABLE IF NOT EXISTS dataset_lineage (
            dataset_id VARCHAR(100) PRIMARY KEY,
            version VARCHAR(50),
            config JSONB,
            row_count BIGINT,
            hash VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        await DBClient.execute(dataset_lineage_query)
        _LOG.info("VERSIONING | Dataset lineage table verified.")

    async def create_version(
        self, dataset_id: str, df: pl.DataFrame, config: dict[str, Any]
    ) -> str:
        """
        Snapshot a dataset version and generate a lineage record.

        Args:
            dataset_id: Unique identifier for this dataset.
            df: The Polars DataFrame to version.
            config: The configuration/query used to generate the dataset.

        Returns:
            str: The generated version string (ISO timestamp + hash).
        """
        row_count = len(df)

        # Simple hash of the data (using first 100 rows and column names for speed)
        # or just hash the config if the data is massive
        config_str = json.dumps(config, sort_keys=True)
        data_sample = str(df.head(100))
        data_hash = hashlib.sha256((config_str + data_sample).encode()).hexdigest()

        version = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{data_hash[:8]}"

        query = """
        INSERT INTO dataset_lineage (dataset_id, version, config, row_count, hash, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (dataset_id) DO UPDATE SET
            version = EXCLUDED.version,
            config = EXCLUDED.config,
            row_count = EXCLUDED.row_count,
            hash = EXCLUDED.hash,
            created_at = EXCLUDED.created_at;
        """
        await DBClient.execute(
            query, dataset_id, version, config_str, row_count, data_hash, datetime.utcnow()
        )
        _LOG.info(f"VERSIONING | Snapshot dataset '{dataset_id}' (version: {version}).")
        return version

    async def get_version_metadata(self, dataset_id: str) -> dict[str, Any] | None:
        """
        Retrieve metadata snapshot for a specific dataset version.

        Args:
            dataset_id: ID of the dataset to look up.

        Returns:
            Dictionary containing version metadata or None if not found.
        """
        query = "SELECT * FROM dataset_lineage WHERE dataset_id = $1"
        row = await DBClient.fetchrow(query, dataset_id)
        if not row:
            return None

        result = dict(row)
        if isinstance(result["config"], str):
            result["config"] = json.loads(result["config"])
        return result
