from __future__ import annotations

import numpy as np


def maximal_marginal_relevance(
    query_vector: list[float],
    candidate_vectors: list[list[float]],
    candidate_indices: list[int],
    top_k: int,
    lambda_mult: float = 0.5,
) -> list[int]:
    """
    Rerank candidate indices by MMR (§2.3, lambda=0.5 default).
    Returns indices into the original candidate lists.
    """
    if not candidate_indices:
        return []
    if len(candidate_indices) <= top_k:
        return candidate_indices

    query = np.array(query_vector, dtype=np.float32)
    vectors = np.array(candidate_vectors, dtype=np.float32)

    selected: list[int] = []
    remaining = list(candidate_indices)

    while remaining and len(selected) < top_k:
        best_idx: int | None = None
        best_score = -np.inf
        for idx in remaining:
            relevance = float(np.dot(query, vectors[idx]))
            diversity_penalty = 0.0
            if selected:
                diversity_penalty = max(float(np.dot(vectors[idx], vectors[s])) for s in selected)
            score = lambda_mult * relevance - (1 - lambda_mult) * diversity_penalty
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is None:
            selected.extend(remaining[: top_k - len(selected)])
            break
        selected.append(best_idx)
        remaining.remove(best_idx)

    return selected
