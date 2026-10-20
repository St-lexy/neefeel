"""
Embedding pipeline for Neefeel's persistent vector memory.

`EmbeddingFunction` is the pluggable interface, so store implementations
never care which embedding model produced a vector. `DeterministicHashEmbedding`
is a network-free stand-in for local dev/tests — it is NOT semantically
meaningful, just stable, so store logic can be exercised without an API key.
`OpenAIEmbedding` is the real one to use in production.
"""

from __future__ import annotations

import hashlib
import math
from typing import List, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingFunction(Protocol):
    def __call__(self, text: str) -> List[float]: ...


class DeterministicHashEmbedding:
    """Offline dev/testing embedding. Same text -> same vector, always —
    but similarity scores are NOT meaningful semantics, just a stable
    fingerprint useful for exercising retrieval-shaped code paths."""

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    def __call__(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        tokens = text.lower().split() or [text.lower()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dimensions):
                vec[i] += digest[i % len(digest)] / 255.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbedding:
    """Real embedding function via any OpenAI-compatible embeddings endpoint."""

    def __init__(self, client, model: str = "text-embedding-3-small"):
        self._client = client
        self.model = model

    def __call__(self, text: str) -> List[float]:
        response = self._client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding
