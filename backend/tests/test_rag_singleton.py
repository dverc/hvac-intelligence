from unittest.mock import patch

from app.api import deps


def test_get_rag_retriever_returns_singleton():
    deps._rag_retriever = None
    with patch("app.api.deps.RAGRetriever") as mock_cls:
        mock_cls.side_effect = lambda: object()
        first = deps.get_rag_retriever()
        second = deps.get_rag_retriever()
        assert first is second
        mock_cls.assert_called_once()
    deps._rag_retriever = None
