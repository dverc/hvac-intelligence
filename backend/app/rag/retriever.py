from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.metrics import observe_rag_retrieval
from app.rag.embedder import get_embedder
from app.rag.mmr import maximal_marginal_relevance
from app.rag.mock_store import LocalMockVectorStore

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Spec-aligned RAG retriever (§2.3, §6 Phase 3).
    Uses raw pinecone-client when configured; falls back to LocalMockVectorStore.
    Applies MMR reranking with lambda from settings (default 0.5).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.embedding_model = self._settings.RAG_EMBEDDING_MODEL
        self.embedding_dim = self._settings.RAG_EMBEDDING_DIM
        self._embedder = get_embedder(self._settings)
        pinecone_key = (self._settings.PINECONE_API_KEY or "").strip()
        self._use_mock = not pinecone_key or pinecone_key.startswith("pc-dev")
        self._mock_store: LocalMockVectorStore | None = None
        self._pinecone_index = None
        self._project_root = Path(__file__).resolve().parents[3]

        if self._use_mock:
            index_path = self._project_root / self._settings.RAG_MOCK_INDEX_PATH
            self._mock_store = LocalMockVectorStore(index_path)
            logger.debug("RAGRetriever using mock store (%s chunks)", self._mock_store.count())
        else:
            from pinecone import Pinecone

            pc = Pinecone(api_key=self._settings.PINECONE_API_KEY)
            self._pinecone_index = pc.Index(self._settings.PINECONE_INDEX_NAME)

    async def embed_query(self, text: str) -> list[float]:
        return await self._embedder.embed_query(text)

    async def retrieve(
        self,
        query: str,
        namespace: Optional[str] = None,
        top_k: int = 5,
        filter_model: Optional[str] = None,
    ) -> list[dict]:
        with observe_rag_retrieval():
            vector = await self.embed_query(query)
            fetch_k = max(top_k * 3, top_k)

            if self._use_mock:
                matches = self._query_mock(vector, fetch_k, namespace, filter_model)
            else:
                matches = self._query_pinecone(vector, fetch_k, namespace, filter_model)

            if not matches:
                return []

            candidate_vectors = [m["_vector"] for m in matches]
            indices = list(range(len(matches)))
            selected = maximal_marginal_relevance(
                query_vector=vector,
                candidate_vectors=candidate_vectors,
                candidate_indices=indices,
                top_k=top_k,
                lambda_mult=self._settings.RAG_MMR_LAMBDA,
            )

            results: list[dict] = []
            for idx in selected:
                match = matches[idx]
                metadata = match.get("metadata", {})
                results.append(
                    {
                        "chunk_id": match["id"],
                        "text": metadata.get("text", ""),
                        "source": metadata.get("source", ""),
                        "similarity_score": match["score"],
                        "namespace": metadata.get("namespace", namespace or "default"),
                    }
                )
            return results

    def _query_mock(
        self,
        vector: list[float],
        top_k: int,
        namespace: Optional[str],
        filter_model: Optional[str],
    ) -> list[dict[str, Any]]:
        if self._mock_store is None:
            return []
        metadata_filter: dict[str, Any] | None = None
        if filter_model:
            metadata_filter = {"equipment_model": {"$eq": filter_model}}
        raw = self._mock_store.query(
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            metadata_filter=metadata_filter,
        )
        return [
            {
                "id": item["id"],
                "score": item["score"],
                "metadata": item.get("metadata", {}),
                "_vector": item["vector"],
            }
            for item in raw
        ]

    def _query_pinecone(
        self,
        vector: list[float],
        top_k: int,
        namespace: Optional[str],
        filter_model: Optional[str],
    ) -> list[dict[str, Any]]:
        if self._pinecone_index is None:
            return []

        query_kwargs: dict[str, Any] = {
            "vector": vector,
            "top_k": top_k,
            "include_metadata": True,
            "include_values": True,
        }
        if namespace:
            query_kwargs["namespace"] = namespace
        if filter_model:
            query_kwargs["filter"] = {"equipment_model": {"$eq": filter_model}}

        response = self._pinecone_index.query(**query_kwargs)
        matches = getattr(response, "matches", None) or []

        return [
            {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata or {},
                "_vector": match.values or vector,
            }
            for match in matches
        ]
