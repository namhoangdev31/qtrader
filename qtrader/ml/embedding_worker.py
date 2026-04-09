from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from qtrader.ml.ollama_adapter import OllamaDecisionAdapter
from qtrader.ml.vector_store import EliteExemplar, memory_store
from qtrader.persistence.db_writer import TradeDBWriter

logger = logging.getLogger("qtrader.ml.embedding_worker")


class AsyncEmbeddingManager:
    _instance: AsyncEmbeddingManager | None = None

    def __new__(cls) -> AsyncEmbeddingManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.worker_task: asyncio.Task[None] | None = None
        self.embedder = OllamaDecisionAdapter(
            model_id=os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")
        )
        self.db_writer = TradeDBWriter()
        self.current_sentiment_vector: list[float] | None = None
        self._initialized = True
        logger.info("[ASYNC_EMBED] Manager initialized")

    async def start(self) -> None:
        if self.worker_task is not None:
            return
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("[ASYNC_EMBED] Background worker started")

    async def stop(self) -> None:
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            logger.info("[ASYNC_EMBED] Background worker stopped")

    def enqueue_note(self, note_id: str, text: str, session_id: str | None = None) -> None:
        try:
            self.queue.put_nowait(
                {"type": "note", "id": note_id, "text": text, "session_id": session_id}
            )
            logger.debug(f"[ASYNC_EMBED] Enqueued note {note_id} for embedding")
        except Exception as e:
            logger.error(f"[ASYNC_EMBED] Failed to enqueue: {e}")

    def refresh_sentiment(self, text: str) -> None:
        try:
            self.queue.put_nowait({"type": "sentiment", "text": text})
            logger.info(f"[ASYNC_EMBED] Enqueued sentiment refresh: {text[:50]}...")
        except Exception as e:
            logger.error(f"[ASYNC_EMBED] Failed to enqueue sentiment: {e}")

    async def _worker_loop(self) -> None:
        while True:
            try:
                task = await self.queue.get()
                t0 = asyncio.get_event_loop().time()
                if task["type"] == "note":
                    note_id = task["id"]
                    text = task["text"]
                    logger.info(f"[ASYNC_EMBED] Embedding note {note_id}...")
                    embedding = await self.embedder.embed(text)
                    if embedding:
                        await self.db_writer.update_note_embedding(note_id, embedding)
                        session_id = task.get("session_id", "manual_intervention")

                        exemplar = EliteExemplar(
                            session_id=session_id,
                            timestamp=datetime.now().isoformat(),
                            market_vector=[0.0, 0.0, 1.0, 1.0],
                            semantic_embedding=embedding,
                            parameters={},
                            performance_score=1.0,
                            expert_notes=text,
                            regime_tag="forensic_intervention",
                        )
                        memory_store.save_exemplar(exemplar)
                        duration = (asyncio.get_event_loop().time() - t0) * 1000
                        logger.info(
                            f"[ASYNC_EMBED] Note {note_id} embedded and "
                            f"synced to RAG in {duration:.2f}ms"
                        )
                    else:
                        logger.error(
                            f"[ASYNC_EMBED] Failed to generate embedding for note {note_id}"
                        )
                elif task["type"] == "sentiment":
                    text = task["text"]
                    logger.info("[ASYNC_EMBED] Updating global sentiment vector...")
                    embedding = await self.embedder.embed(text)
                    if embedding:
                        self.current_sentiment_vector = embedding
                        duration = (asyncio.get_event_loop().time() - t0) * 1000
                        logger.info(
                            f"[ASYNC_EMBED] Sentiment vector updated successfully "
                            f"in {duration:.2f}ms"
                        )
                    else:
                        logger.error("[ASYNC_EMBED] Failed to generate sentiment embedding")
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ASYNC_EMBED] Worker error: {e}")
                await asyncio.sleep(1)


embedding_manager = AsyncEmbeddingManager()
