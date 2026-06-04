from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.rag.chunker import DocumentChunk, split_markdown_file, split_text
from app.rag.constants import RAG_NAMESPACES, get_base_namespace, is_valid_base_namespace
from app.rag.embedder import get_embedder
from app.rag.mock_store import LocalMockVectorStore

logger = logging.getLogger(__name__)


class KnowledgeIndexer:
    """
    Indexes knowledge sources into Pinecone (production) or LocalMockVectorStore (dev).
    Uses raw pinecone-client per §6 Phase 3 — not langchain-pinecone integration.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        force_mock: bool = False,
        project_root: Path | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._project_root = project_root or Path(__file__).resolve().parents[3]
        self._embedder = get_embedder(self._settings, force_mock=force_mock)
        pinecone_key = (self._settings.PINECONE_API_KEY or "").strip()
        self._use_mock = force_mock or not pinecone_key or pinecone_key.startswith("pc-dev")
        self._mock_store: LocalMockVectorStore | None = None
        self._pinecone_index = None

        if self._use_mock:
            index_path = self._project_root / self._settings.RAG_MOCK_INDEX_PATH
            self._mock_store = LocalMockVectorStore(index_path)
            logger.info("RAG indexer using local mock store at %s", index_path)
        else:
            from pinecone import Pinecone

            pc = Pinecone(api_key=self._settings.PINECONE_API_KEY)
            self._pinecone_index = pc.Index(self._settings.PINECONE_INDEX_NAME)
            logger.info(
                "RAG indexer using Pinecone index %s",
                self._settings.PINECONE_INDEX_NAME,
            )

    @property
    def uses_mock(self) -> bool:
        return self._use_mock

    def _chunk_id(self, chunk: DocumentChunk) -> str:
        raw = f"{chunk.namespace}:{chunk.source}:{chunk.chunk_index}:{chunk.text[:64]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def index_chunks(
        self,
        chunks: list[DocumentChunk],
        chunk_ids: list[str] | None = None,
    ) -> int:
        if not chunks:
            return 0

        namespace = chunks[0].namespace
        if not is_valid_base_namespace(namespace):
            raise ValueError(f"Invalid namespace: {namespace}")

        texts = [c.text for c in chunks]
        vectors = await self._embedder.embed_texts(texts)
        if chunk_ids is not None and len(chunk_ids) != len(chunks):
            raise ValueError("chunk_ids length must match chunks length")
        ids = chunk_ids if chunk_ids is not None else [self._chunk_id(c) for c in chunks]
        metadatas: list[dict[str, Any]] = [
            {
                "text": c.text,
                "source": c.source,
                "namespace": c.namespace,
                "chunk_index": c.chunk_index,
                **({"equipment_model": c.equipment_model} if c.equipment_model else {}),
            }
            for c in chunks
        ]

        if self._use_mock:
            assert self._mock_store is not None
            return self._mock_store.upsert(ids, vectors, metadatas, namespace)

        assert self._pinecone_index is not None
        self._pinecone_index.upsert(
            vectors=[
                {"id": chunk_id, "values": vector, "metadata": metadata}
                for chunk_id, vector, metadata in zip(ids, vectors, metadatas)
            ],
            namespace=namespace,
        )
        return len(chunks)

    async def delete_by_id_prefix(self, namespace: str, prefix: str) -> int:
        if not is_valid_base_namespace(namespace):
            raise ValueError(f"Invalid namespace: {namespace}")
        if self._use_mock:
            assert self._mock_store is not None
            return self._mock_store.delete_by_id_prefix(namespace, prefix)

        assert self._pinecone_index is not None
        # Pinecone serverless: list + delete by prefix when available; fallback no-op count.
        try:
            deleted = 0
            for ids_batch in self._list_ids_by_prefix(namespace, prefix):
                if ids_batch:
                    self._pinecone_index.delete(ids=ids_batch, namespace=namespace)
                    deleted += len(ids_batch)
            return deleted
        except Exception as exc:
            logger.warning("Pinecone prefix delete failed: %s", exc)
            return 0

    def _list_ids_by_prefix(self, namespace: str, prefix: str):
        """Yield ID batches matching prefix (Pinecone list API)."""
        assert self._pinecone_index is not None
        pagination_token = None
        while True:
            kwargs: dict[str, Any] = {"namespace": namespace, "prefix": prefix}
            if pagination_token:
                kwargs["pagination_token"] = pagination_token
            response = self._pinecone_index.list_paginated(**kwargs)
            ids = [item.id for item in (response.vectors or []) if item.id.startswith(prefix)]
            if ids:
                yield ids
            pagination_token = getattr(response, "pagination", None)
            if pagination_token is None or not getattr(pagination_token, "next", None):
                break
            pagination_token = pagination_token.next

    def get_namespace_counts(self, org_slug: str | None = None) -> dict[str, int]:
        """Return vector counts keyed by base namespace (optionally scoped to one org)."""
        if self._use_mock:
            assert self._mock_store is not None
            if org_slug:
                return self._mock_store.count_by_org_prefix(
                    org_slug, sorted(RAG_NAMESPACES)
                )
            return self._mock_store.count_by_base_namespaces(sorted(RAG_NAMESPACES))

        assert self._pinecone_index is not None
        stats = self._pinecone_index.describe_index_stats()
        ns_stats = getattr(stats, "namespaces", None) or {}
        counts = {base: 0 for base in RAG_NAMESPACES}
        for ns, info in ns_stats.items():
            base = get_base_namespace(ns)
            if base not in RAG_NAMESPACES:
                continue
            if org_slug and not ns.startswith(f"{org_slug}::"):
                continue
            count = int(getattr(info, "vector_count", 0) or info.get("vector_count", 0))
            counts[base] = counts.get(base, 0) + count
        return counts

    async def index_directory(
        self,
        source_dir: Path,
        namespace: str,
        pattern: str = "*.md",
    ) -> int:
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")

        total = 0
        for path in sorted(source_dir.glob(pattern)):
            if path.is_file():
                chunks = split_markdown_file(path, namespace=namespace)
                total += await self.index_chunks(chunks)
        return total

    async def index_text_file(
        self,
        path: Path,
        namespace: str,
        equipment_model: str | None = None,
    ) -> int:
        content = path.read_text(encoding="utf-8")
        chunks = split_text(
            text=content,
            source=str(path),
            namespace=namespace,
            equipment_model=equipment_model,
        )
        return await self.index_chunks(chunks)
