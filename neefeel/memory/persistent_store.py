"""
Persistent semantic memory interface, shared by the local dev backend and
the production Pinecone backend.

Unlike a plain key-value store, this is built for semantic retrieval: text
goes in, gets embedded, and queries retrieve by similarity — "query past
work semantically rather than relying on exact keyword matching."
"""

from __future__ import annotations

import abc
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .embeddings import EmbeddingFunction


@dataclass
class MemoryRecord:
    key: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None


class PersistentMemoryStore(abc.ABC):
    @abc.abstractmethod
    async def upsert(
        self, namespace: str, key: str, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        ...

    @abc.abstractmethod
    async def get(self, namespace: str, key: str) -> Optional[MemoryRecord]:
        ...

    @abc.abstractmethod
    async def semantic_query(
        self, namespace: str, query_text: str, top_k: int = 5
    ) -> List[MemoryRecord]:
        ...

    @abc.abstractmethod
    async def list_all(self, namespace: str) -> List[MemoryRecord]:
        ...


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (norm_a * norm_b)


class InMemoryPersistentStore(PersistentMemoryStore):
    """Local dev backend: real cosine-similarity search over embeddings held
    in process memory. Same retrieval semantics as Pinecone, zero network —
    swap in `PineconeMemoryStore` for cross-session persistence with no
    other code changes, since both implement this same interface."""

    def __init__(self, embed_fn: EmbeddingFunction):
        self._embed = embed_fn
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def upsert(
        self, namespace: str, key: str, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        bucket = self._data.setdefault(namespace, {})
        bucket[key] = {"text": text, "metadata": metadata or {}, "embedding": self._embed(text)}

    async def get(self, namespace: str, key: str) -> Optional[MemoryRecord]:
        entry = self._data.get(namespace, {}).get(key)
        if entry is None:
            return None
        return MemoryRecord(key=key, text=entry["text"], metadata=entry["metadata"])

    async def semantic_query(
        self, namespace: str, query_text: str, top_k: int = 5
    ) -> List[MemoryRecord]:
        bucket = self._data.get(namespace, {})
        if not bucket:
            return []
        query_vec = self._embed(query_text)
        scored = [
            MemoryRecord(
                key=k,
                text=v["text"],
                metadata=v["metadata"],
                score=_cosine_similarity(query_vec, v["embedding"]),
            )
            for k, v in bucket.items()
        ]
        scored.sort(key=lambda r: r.score or 0.0, reverse=True)
        return scored[:top_k]

    async def list_all(self, namespace: str) -> List[MemoryRecord]:
        bucket = self._data.get(namespace, {})
        return [MemoryRecord(key=k, text=v["text"], metadata=v["metadata"]) for k, v in bucket.items()]
