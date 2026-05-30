import json

import pytest

from app.rag.embedder import _hash_to_vector
from app.rag.retriever import RAGRetriever


@pytest.fixture
def mock_index_path(tmp_path, monkeypatch):
    """Isolated mock vector index with multiple namespaces."""
    index_path = tmp_path / "test_mock_index.json"
    dim = 64
    monkeypatch.setenv("RAG_EMBEDDING_DIM", str(dim))
    monkeypatch.setenv("RAG_MOCK_INDEX_PATH", str(index_path))
    monkeypatch.setenv("PINECONE_API_KEY", "pc-dev-test")

    records = []
    texts = [
        ("faq_general", "Warranty covers parts for 5 years"),
        ("faq_general", "Annual maintenance plan includes two visits"),
        ("faq_billing", "Payment plans available for repairs over $500"),
        ("equipment_docs", "Carrier Infinity requires filter size 20x25x4"),
    ]
    for idx, (namespace, text) in enumerate(texts):
        vector = _hash_to_vector(text, dim)
        records.append(
            {
                "id": f"chunk-{idx}",
                "namespace": namespace,
                "vector": vector,
                "metadata": {
                    "text": text,
                    "source": f"{namespace}.md",
                    "namespace": namespace,
                },
            }
        )

    index_path.write_text(json.dumps({"records": records}), encoding="utf-8")
    from app.core.config import get_settings

    get_settings.cache_clear()
    return index_path


@pytest.mark.asyncio
async def test_retrieve_returns_top_k(mock_index_path):
    retriever = RAGRetriever()
    results = await retriever.retrieve("warranty coverage", namespace="faq_general", top_k=2)
    assert len(results) >= 1
    assert results[0]["text"]
    assert "similarity_score" in results[0]


@pytest.mark.asyncio
async def test_mmr_reduces_redundancy(mock_index_path):
    retriever = RAGRetriever()
    results = await retriever.retrieve("maintenance plan warranty", namespace="faq_general", top_k=2)
    texts = [item["text"] for item in results]
    assert len(set(texts)) == len(texts), "MMR should return diverse chunks"


@pytest.mark.asyncio
async def test_namespace_filter_scopes_results(mock_index_path):
    retriever = RAGRetriever()
    billing = await retriever.retrieve("payment plan", namespace="faq_billing", top_k=3)
    assert billing
    assert all(r["namespace"] == "faq_billing" for r in billing)


@pytest.mark.asyncio
async def test_missing_namespace_returns_empty(mock_index_path):
    retriever = RAGRetriever()
    results = await retriever.retrieve("anything", namespace="nonexistent_ns", top_k=5)
    assert results == []
