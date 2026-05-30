from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class LocalMockVectorStore:
    """
    File-backed vector store for local development without Pinecone credentials.
  Stores chunk vectors + metadata keyed by namespace.
    """

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.index_path.exists():
            self._records = []
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            self._records = payload.get("records", [])
        except json.JSONDecodeError:
            logger.warning("Corrupt mock index at %s; resetting", self.index_path)
            self._records = []

    def save(self) -> None:
        self.index_path.write_text(
            json.dumps({"records": self._records}, indent=2),
            encoding="utf-8",
        )

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadatas: list[dict[str, Any]],
        namespace: str,
    ) -> int:
        by_id = {record["id"]: record for record in self._records if record["namespace"] == namespace}
        for chunk_id, vector, metadata in zip(ids, vectors, metadatas, strict=True):
            by_id[chunk_id] = {
                "id": chunk_id,
                "namespace": namespace,
                "vector": vector,
                "metadata": metadata,
            }
        other = [r for r in self._records if r["namespace"] != namespace]
        self._records = other + list(by_id.values())
        self.save()
        return len(ids)

    def query(
        self,
        vector: list[float],
        top_k: int = 5,
        namespace: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        candidates = self._records
        if namespace:
            candidates = [r for r in candidates if r["namespace"] == namespace]
        if metadata_filter:
            for key, expected in metadata_filter.items():
                if isinstance(expected, dict) and "$eq" in expected:
                    expected = expected["$eq"]
                candidates = [
                    r for r in candidates if r.get("metadata", {}).get(key) == expected
                ]

        if not candidates:
            return []

        query_vec = np.array(vector, dtype=np.float32)
        scored: list[tuple[float, dict[str, Any]]] = []
        for record in candidates:
            vec = np.array(record["vector"], dtype=np.float32)
            denom = np.linalg.norm(query_vec) * np.linalg.norm(vec)
            score = float(np.dot(query_vec, vec) / denom) if denom > 0 else 0.0
            scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "id": record["id"],
                "score": score,
                "metadata": record.get("metadata", {}),
                "vector": record["vector"],
            }
            for score, record in scored[:top_k]
        ]

    def count(self, namespace: str | None = None) -> int:
        if namespace is None:
            return len(self._records)
        return sum(1 for r in self._records if r["namespace"] == namespace)
