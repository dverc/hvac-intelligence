from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.rag.chunker import DocumentChunk, split_markdown_file, split_text
from app.rag.constants import RAG_NAMESPACES
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

    async def index_chunks(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0

        namespace = chunks[0].namespace
        if namespace not in RAG_NAMESPACES:
            raise ValueError(f"Invalid namespace: {namespace}")

        texts = [c.text for c in chunks]
        vectors = await self._embedder.embed_texts(texts)
        ids = [self._chunk_id(c) for c in chunks]
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
        self._pinecone_index.upsert(vectors=vectors, ids=ids, metadatas=metadatas, namespace=namespace)
        return len(chunks)

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
