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
    """RAG-enabled vector store for QTrader using DuckDB.
    
    Stores market regimes and successful parameter sets as 'Elite Exemplars'.
    Allows AI to retrieve past successful templates for the current context.
    """

    def __init__(self, db_path: str = "data/institutional_memory.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize DuckDB tables for vector storage."""
        import os
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            logger.info(f"[VECTOR_STORE] Created data directory: {parent_dir}")
            
        conn = duckdb.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exemplars (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id VARCHAR,
                timestamp TIMESTAMP,
                market_vector FLOAT[],
                semantic_embedding FLOAT[],
                parameters JSON,
                performance_score FLOAT,
                expert_notes TEXT,
                regime_tag VARCHAR
            )
        """)
        conn.close()

    def save_exemplar(self, exemplar: EliteExemplar) -> None:
        """Persist a new elite parameter template."""
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO exemplars (session_id, timestamp, market_vector, semantic_embedding, parameters, performance_score, expert_notes, regime_tag) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    exemplar.session_id,
                    exemplar.timestamp,
                    exemplar.market_vector,
                    exemplar.semantic_embedding,
                    json.dumps(exemplar.parameters),
                    exemplar.performance_score,
                    exemplar.expert_notes,
                    exemplar.regime_tag
                ]
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
        top_k: int = 3
    ) -> list[dict[str, Any]]:
        """Retrieve similar past successful parameter sets."""
        conn = duckdb.connect(self.db_path)
        try:
            # Combined similarity: 0.7 Weight Market Logic + 0.3 Weight Semantic Context
            # Using DuckDB list_cosine_similarity for native vector search
            
            sql = """
                SELECT 
                    parameters, 
                    expert_notes, 
                    performance_score,
                    regime_tag,
                    list_cosine_similarity(market_vector, ?::FLOAT[]) as market_sim
            """
            params: list[Any] = [market_vector]

            if semantic_embedding:
                sql += ", list_cosine_similarity(semantic_embedding, ?::FLOAT[]) as semantic_sim "
                params.append(semantic_embedding)
                sql += "FROM exemplars ORDER BY (0.7 * market_sim + 0.3 * semantic_sim) DESC LIMIT ?"
            else:
                sql += "FROM exemplars ORDER BY market_sim DESC LIMIT ?"
            
            params.append(top_k)
            
            results = conn.execute(sql, params).fetchall()
            
            templates = []
            for row in results:
                templates.append({
                    "parameters": json.loads(row[0]),
                    "notes": row[1],
                    "score": row[2],
                    "regime": row[3],
                    "similarity": row[4] if not semantic_embedding else (0.7 * row[4] + 0.3 * row[5])
                })
            return templates
        except Exception as e:
            logger.error(f"[VECTOR_DB] Retrieval failed: {e}")
            return []
        finally:
            conn.close()

# Global Singleton
memory_store = InstitutionalMemoryStore()
