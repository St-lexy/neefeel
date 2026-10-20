"""
Phase 4 (persistent): Scoped 3-Tier Company Memory.

Tier 1 (Global) and Tier 2 (Department) live in a `PersistentMemoryStore`
(Pinecone in production, `InMemoryPersistentStore` for local dev) and are
retrieved semantically. Tier 3 (Task) is deliberately NOT vectorized — it's
ephemeral, dependency-bound context, so it lives in a plain in-process dict
that's discarded at the end of a run, and upstream predecessor output is
passed straight into a downstream dependent's prompt with no round trip
through the vector store.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import Department, StructuredTask
from .persistent_store import MemoryRecord, PersistentMemoryStore

GLOBAL_NAMESPACE = "neefeel-global"
MAX_FACT_CHARS = 4000  # bound what one department fact can add to later prompts


def department_namespace(department: Department) -> str:
    return f"neefeel-{department.value}"


class CompanyMemory:
    def __init__(self, store: PersistentMemoryStore, semantic_top_k: int = 5):
        self._store = store
        self._top_k = semantic_top_k
        self._task_context: Dict[str, Dict[str, Any]] = {}  # ephemeral, never persisted

    # -- Tier 1: Global (immutable venture anchors) ----------------------------------
    async def set_global(self, key: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        await self._store.upsert(GLOBAL_NAMESPACE, key, text, metadata)

    async def seed_global_identity(
        self, company_name: str, mission: str, vision: str, brand_assets: Optional[List[str]] = None
    ) -> None:
        await self.set_global("company_name", company_name)
        await self.set_global("mission", mission)
        await self.set_global("vision", vision)
        if brand_assets:
            await self.set_global("brand_assets", "; ".join(brand_assets))

    async def get_global_context(self, query_text: str) -> List[MemoryRecord]:
        return await self._store.semantic_query(GLOBAL_NAMESPACE, query_text, self._top_k)

    # -- Tier 2: Department (isolated per-department namespace) ------------------------
    async def record_department_fact(
        self, department: Department, key: str, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        await self._store.upsert(department_namespace(department), key, text, metadata)

    async def get_department_context(self, department: Department, query_text: str) -> List[MemoryRecord]:
        return await self._store.semantic_query(department_namespace(department), query_text, self._top_k)

    async def record_result_as_department_fact(
        self, task: StructuredTask, summary: str, run_id: Optional[str] = None
    ) -> None:
        """Task ids (T1, T2 ...) repeat across runs, so the key is namespaced by
        run id; otherwise a new run silently overwrites the previous run's facts."""
        key = f"{run_id}:{task.task_id}" if run_id else task.task_id
        await self.record_department_fact(
            task.department, key, summary[:MAX_FACT_CHARS],
            metadata={"task_id": task.task_id, "title": task.title, "run_id": run_id or ""},
        )

    async def query_all_scopes(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic search across the global namespace AND every department
        namespace, merged and re-ranked by score. This deliberately breaks
        department isolation — it's for the founder-facing `AICofounder.chat()`
        assistant, which is allowed to see across the whole venture, not for
        task dispatch (which must keep using `build_context_for_task`, the
        only method that respects per-department isolation)."""
        all_hits: List[MemoryRecord] = list(await self.get_global_context(query_text))
        for department in Department:
            all_hits.extend(await self.get_department_context(department, query_text))
        all_hits.sort(key=lambda r: r.score if r.score is not None else 0.0, reverse=True)
        return [
            {"content": r.text, "score": r.score, "metadata": r.metadata}
            for r in all_hits[:top_k]
        ]

    # -- Tier 3: Task (ephemeral, dependency-bound, never vectorized) -------------------
    def record_task_context(self, task_id: str, key: str, value: Any) -> None:
        self._task_context.setdefault(task_id, {})[key] = value

    def get_task_context(self, task_id: str) -> Dict[str, Any]:
        return dict(self._task_context.get(task_id, {}))

    def pass_upstream_output(
        self, upstream_task_id: str, downstream_task_id: str, output: str, label: Optional[str] = None
    ) -> None:
        """Tier 3: hands an upstream task's output straight to one downstream task.
        It is stored where `get_task_context` / `build_context_for_task` read it,
        so the downstream executive actually receives it."""
        self.record_task_context(downstream_task_id, label or upstream_task_id, output)

    def reset_task_context(self) -> None:
        """Tier 3 is per-run; call at the start of every run."""
        self._task_context.clear()

    # -- Composed context for dispatch ----------------------------------------------------
    async def build_context_for_task(self, task: StructuredTask) -> Dict[str, Any]:
        """The only method executives call. Global + this department's
        semantic history + this task's direct upstream context — nothing
        from any other department's namespace."""
        global_hits = await self.get_global_context(task.instruction)
        dept_hits = await self.get_department_context(task.department, task.instruction)
        return {
            "global": [r.text for r in global_hits],
            "department_history": [r.text for r in dept_hits],
            "task": self.get_task_context(task.task_id),
        }
