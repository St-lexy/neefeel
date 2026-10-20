"""
Production persistent memory backend: Pinecone.

Namespace mapping:
  - Global scope -> "neefeel-global"                (Tier 1, every department reads)
  - Department   -> "neefeel-{department}"           (Tier 2, isolated per dept)

Task-scoped context (Tier 3) deliberately does NOT live here — it's
ephemeral and dependency-bound, so it stays in the in-process dict in
`scopes.py` and is passed directly into the downstream dependent's prompt,
per the "vectorized or passed directly" design choice in the spec.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .embeddings import EmbeddingFunction
from .persistent_store import MemoryRecord, PersistentMemoryStore


class PineconeMemoryStore(PersistentMemoryStore):
    def __init__(
        self,
        api_key: str,
        index_name: str,
        embed_fn: EmbeddingFunction,
        cloud: str = "aws",
        region: str = "us-east-1",
        dimension: int = 1536,
    ):
        try:
            from pinecone import Pinecone, ServerlessSpec
        except ImportError as exc:
            raise ImportError(
                "The 'pinecone' package is required for PineconeMemoryStore. "
                "Install it with: pip install pinecone"
            ) from exc

        self._embed = embed_fn
        actual_dim = len(embed_fn("dimension probe"))
        if actual_dim != dimension:
            raise ValueError(
                f"Embedding function produces {actual_dim}-dim vectors but the index "
                f"dimension is {dimension}. Pass dimension={actual_dim} or use a matching embedder."
            )
        self._pc = Pinecone(api_key=api_key)

        existing = {idx["name"] for idx in self._pc.list_indexes()}
        if index_name not in existing:
            self._pc.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=cloud, region=region),
            )
        self._index = self._pc.Index(index_name)

    @staticmethod
    def _vector_id(namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    async def upsert(
        self, namespace: str, key: str, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        vector = await asyncio.to_thread(self._embed, text)
        # Pinecone metadata is capped (~40KB per vector); keep headroom.
        meta = {**(metadata or {}), "text": text[:30000], "key": key}
        await asyncio.to_thread(
            self._index.upsert,
            vectors=[{"id": self._vector_id(namespace, key), "values": vector, "metadata": meta}],
            namespace=namespace,
        )

    async def get(self, namespace: str, key: str) -> Optional[MemoryRecord]:
        result = await asyncio.to_thread(
            self._index.fetch, ids=[self._vector_id(namespace, key)], namespace=namespace
        )
        vectors = getattr(result, "vectors", {}) or {}
        match = vectors.get(self._vector_id(namespace, key))
        if match is None:
            return None
        meta = match.get("metadata", {}) if isinstance(match, dict) else match.metadata
        return MemoryRecord(key=key, text=meta.get("text", ""), metadata=meta)

    async def semantic_query(
        self, namespace: str, query_text: str, top_k: int = 5
    ) -> List[MemoryRecord]:
        query_vec = await asyncio.to_thread(self._embed, query_text)
        response = await asyncio.to_thread(
            self._index.query,
            vector=query_vec, top_k=top_k, namespace=namespace, include_metadata=True,
        )
        records = []
        for match in getattr(response, "matches", []):
            meta = match.metadata or {}
            records.append(
                MemoryRecord(
                    key=meta.get("key", match.id),
                    text=meta.get("text", ""),
                    metadata=meta,
                    score=match.score,
                )
            )
        return records

    async def list_all(self, namespace: str) -> List[MemoryRecord]:
        # Pinecone has no cheap "dump every vector" primitive; serverless
        # indexes support id listing on recent SDK versions. Best-effort:
        # list ids, then fetch. Falls back to empty if unsupported.
        try:
            ids = [vid for page in self._index.list(namespace=namespace) for vid in page]
            if not ids:
                return []
            fetched = self._index.fetch(ids=ids, namespace=namespace)
            vectors = getattr(fetched, "vectors", {}) or {}
            records = []
            for vid, v in vectors.items():
                meta = v.get("metadata", {}) if isinstance(v, dict) else v.metadata
                records.append(MemoryRecord(key=meta.get("key", vid), text=meta.get("text", ""), metadata=meta))
            return records
        except Exception:
            return []
