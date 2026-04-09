from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from typing import Any
import duckdb

logger = logging.getLogger("qtrader.ml.vector_store")


@dataclass
class EliteExemplar:
    session_id: str
    timestamp: str
    market_vector: list[float]
    semantic_embedding: list[float]
    parameters: dict[str, Any]
    performance_score: float
    expert_notes: str
    regime_tag: str = "forensic"


class InstitutionalMemoryStore:
    def __init__(self, db_path: str = "data/institutional_memory.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        import os

        parent_dir = os.path.dirname(self.db_path)
        if parent_dir and (not os.path.exists(parent_dir)):
            os.makedirs(parent_dir, exist_ok=True)
            logger.info(f"[VECTOR_STORE] Created data directory: {parent_dir}")
        conn = duckdb.connect(self.db_path)
        conn.execute(
            "\n            CREATE TABLE IF NOT EXISTS exemplars (\n                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n                session_id VARCHAR,\n                timestamp TIMESTAMP,\n                market_vector FLOAT[],\n                semantic_embedding FLOAT[],\n                parameters JSON,\n                performance_score FLOAT,\n                expert_notes TEXT,\n                regime_tag VARCHAR\n            )\n        "
        )
        conn.close()

    def save_exemplar(self, exemplar: EliteExemplar) -> None:
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO exemplars (session_id, timestamp, market_vector, semantic_embedding, parameters, performance_score, expert_notes, regime_tag) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    exemplar.session_id,
                    exemplar.timestamp,
                    exemplar.market_vector,
                    exemplar.semantic_embedding,
                    json.dumps(exemplar.parameters),
                    exemplar.performance_score,
                    exemplar.expert_notes,
                    exemplar.regime_tag,
                ],
            )
            logger.info(f"[VECTOR_DB] Saved Elite Exemplar for session {exemplar.session_id}")
        except Exception as e:
            logger.error(f"[VECTOR_DB] Save failed: {e}")
        finally:
            conn.close()

    def retrieve_similar(
        self,
        market_vector: list[float],
        semantic_embedding: list[float] | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        conn = duckdb.connect(self.db_path)
        try:
            sql = "\n                SELECT\n                    parameters,\n                    expert_notes,\n                    performance_score,\n                    regime_tag,\n                    list_cosine_similarity(market_vector, ?::FLOAT[]) as market_sim\n            "
            params: list[Any] = [market_vector]
            if semantic_embedding:
                sql += ", list_cosine_similarity(semantic_embedding, ?::FLOAT[]) as semantic_sim "
                params.append(semantic_embedding)
                sql += (
                    "FROM exemplars ORDER BY (0.7 * market_sim + 0.3 * semantic_sim) DESC LIMIT ?"
                )
            else:
                sql += "FROM exemplars ORDER BY market_sim DESC LIMIT ?"
            params.append(top_k)
            results = conn.execute(sql, params).fetchall()
            templates = []
            for row in results:
                templates.append(
                    {
                        "parameters": json.loads(row[0]),
                        "notes": row[1],
                        "score": row[2],
                        "regime": row[3],
                        "similarity": row[4]
                        if not semantic_embedding
                        else 0.7 * row[4] + 0.3 * row[5],
                    }
                )
            return templates
        except Exception as e:
            logger.error(f"[VECTOR_DB] Retrieval failed: {e}")
            return []
        finally:
            conn.close()


memory_store = InstitutionalMemoryStore()
