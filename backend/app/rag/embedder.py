from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np

from app.core.config import Settings, get_settings


class BaseEmbedder(ABC):
    embedding_dim: int

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.embedding_dim = self._settings.RAG_EMBEDDING_DIM
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            input=texts,
            model=self._settings.RAG_EMBEDDING_MODEL,
        )
        return [item.embedding for item in response.data]


class MockEmbedder(BaseEmbedder):
    """Deterministic local embeddings for E2E indexing without API keys."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.embedding_dim = self._settings.RAG_EMBEDDING_DIM

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hash_to_vector(text, self.embedding_dim) for text in texts]


def _hash_to_vector(text: str, dim: int) -> list[float]:
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = np.random.RandomState(seed)
    arr = rng.randn(dim).astype(np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def get_embedder(settings: Settings | None = None, force_mock: bool = False) -> BaseEmbedder:
    settings = settings or get_settings()
    api_key = (settings.OPENAI_API_KEY or "").strip()
    placeholder = api_key.startswith("sk-dev") or api_key.endswith("placeholder")
    if force_mock or not api_key or placeholder:
        return MockEmbedder(settings)
    try:
        return OpenAIEmbedder(settings)
    except ImportError:
        return MockEmbedder(settings)
