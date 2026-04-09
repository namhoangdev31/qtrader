import hashlib
import json
import logging
from datetime import datetime
from typing import Any

import polars as pl

from qtrader.core.db import DBClient

_LOG = logging.getLogger(__name__)


class VersionManager:
    async def initialize(self) -> None:
        dataset_lineage_query = "\n        CREATE TABLE IF NOT EXISTS dataset_lineage (\n            dataset_id VARCHAR(100) PRIMARY KEY,\n            version VARCHAR(50),\n            config JSONB,\n            row_count BIGINT,\n            hash VARCHAR(64),\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n        );\n        "
        await DBClient.execute(dataset_lineage_query)
        _LOG.info("VERSIONING | Dataset lineage table verified.")

    async def create_version(
        self, dataset_id: str, df: pl.DataFrame, config: dict[str, Any]
    ) -> str:
        row_count = len(df)
        config_str = json.dumps(config, sort_keys=True)
        data_sample = str(df.head(100))
        data_hash = hashlib.sha256((config_str + data_sample).encode()).hexdigest()
        version = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{data_hash[:8]}"
        query = "\n        INSERT INTO dataset_lineage (dataset_id, version, config, row_count, hash, created_at)\n        VALUES ($1, $2, $3, $4, $5, $6)\n        ON CONFLICT (dataset_id) DO UPDATE SET\n            version = EXCLUDED.version,\n            config = EXCLUDED.config,\n            row_count = EXCLUDED.row_count,\n            hash = EXCLUDED.hash,\n            created_at = EXCLUDED.created_at;\n        "
        await DBClient.execute(
            query, dataset_id, version, config_str, row_count, data_hash, datetime.utcnow()
        )
        _LOG.info(f"VERSIONING | Snapshot dataset '{dataset_id}' (version: {version}).")
        return version

    async def get_version_metadata(self, dataset_id: str) -> dict[str, Any] | None:
        query = "SELECT * FROM dataset_lineage WHERE dataset_id = $1"
        row = await DBClient.fetchrow(query, dataset_id)
        if not row:
            return None
        result = dict(row)
        if isinstance(result["config"], str):
            result["config"] = json.loads(result["config"])
        return result
