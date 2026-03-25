import json
import logging
from datetime import datetime
from typing import Any

from qtrader.core.db import DBClient

_LOG = logging.getLogger(__name__)


class LineageStore:
    """
    Handles persistence of feature and dataset lineage records.
    Ensures that every feature and model can be traced back to its raw sources.
    """

    async def initialize(self) -> None:
        """Create lineage tables if they don't exist."""
        feature_lineage_query = """
        CREATE TABLE IF NOT EXISTS feature_lineage (
            feature_name VARCHAR(100) PRIMARY KEY,
            source_columns JSONB,
            dataset_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        await DBClient.execute(feature_lineage_query)
        _LOG.info("LINEAGE | Feature lineage table verified.")

    async def record_feature(
        self, feature_name: str, source_columns: list[str], dataset_id: str
    ) -> None:
        """
        Record the lineage for a newly created feature.

        Args:
            feature_name: Unique name of the feature.
            source_columns: List of columns used to derive this feature.
            dataset_id: ID of the dataset this feature belongs to.
        """
        query = """
        INSERT INTO feature_lineage (feature_name, source_columns, dataset_id, created_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (feature_name) DO UPDATE SET
            source_columns = EXCLUDED.source_columns,
            dataset_id = EXCLUDED.dataset_id,
            created_at = EXCLUDED.created_at;
        """
        await DBClient.execute(
            query, feature_name, json.dumps(source_columns), dataset_id, datetime.utcnow()
        )
        _LOG.info(f"LINEAGE | Recorded feature '{feature_name}' lineage.")

    async def get_feature_lineage(self, feature_name: str) -> dict[str, Any] | None:
        """
        Retrieve lineage information for a specific feature.

        Args:
            feature_name: Name of the feature to look up.

        Returns:
            Dictionary containing lineage metadata or None if not found.
        """
        query = "SELECT * FROM feature_lineage WHERE feature_name = $1"
        row = await DBClient.fetchrow(query, feature_name)
        if not row:
            return None

        result = dict(row)
        if isinstance(result["source_columns"], str):
            result["source_columns"] = json.loads(result["source_columns"])
        return result
