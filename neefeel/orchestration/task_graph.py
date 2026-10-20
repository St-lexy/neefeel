"""
Phase 1: Task & Event Orchestration — the DAG itself.

Independent tasks become nodes with no edge between them, so the engine runs
them in parallel. Dependent tasks get a `depends_on` edge, so the engine won't
dispatch a node until every predecessor is COMPLETED.
"""

from __future__ import annotations

from typing import Dict, List

from ..models import StructuredTask, TaskStatus


class CyclicDependencyError(Exception):
    pass


_BLOCKING = {TaskStatus.FAILED, TaskStatus.BLOCKED_ON_HITL, TaskStatus.BLOCKED_ON_DEPENDENCY}


class TaskGraph:
    def __init__(self, tasks: List[StructuredTask]):
        seen = set()
        for t in tasks:
            if t.task_id in seen:
                raise ValueError(f"Duplicate task_id '{t.task_id}' in plan")
            seen.add(t.task_id)
        self._nodes: Dict[str, StructuredTask] = {t.task_id: t for t in tasks}
        self._validate_no_cycles()

    # -- Construction / validation ---------------------------------------------
    def _validate_no_cycles(self) -> None:
        for task in self._nodes.values():
            for dep in task.depends_on:
                if dep not in self._nodes:
                    raise ValueError(f"Task '{task.task_id}' depends on unknown task '{dep}'")

        visiting, visited = set(), set()

        def dfs(task_id: str):
            if task_id in visited:
                return
            if task_id in visiting:
                raise CyclicDependencyError(f"Cycle detected at task '{task_id}'")
            visiting.add(task_id)
            for dep in self._nodes[task_id].depends_on:
                dfs(dep)
            visiting.discard(task_id)
            visited.add(task_id)

        for task_id in self._nodes:
            dfs(task_id)

    # -- Queries ------------------------------------------------------------------
    @property
    def tasks(self) -> List[StructuredTask]:
        return list(self._nodes.values())

    def get(self, task_id: str) -> StructuredTask:
        return self._nodes[task_id]

    @property
    def tasks_by_id(self) -> Dict[str, StructuredTask]:
        return dict(self._nodes)

    def refresh_dependency_states(self) -> None:
        """Re-derives PENDING <-> BLOCKED_ON_DEPENDENCY for every not-yet-started
        task from its dependencies' current status. Re-evaluating (instead of
        latching) is what lets downstream work resume after a founder approves
        an upstream task. Blocking propagates transitively."""
        changed = True
        while changed:
            changed = False
            for task in self._nodes.values():
                if task.status not in (TaskStatus.PENDING, TaskStatus.BLOCKED_ON_DEPENDENCY):
                    continue
                deps = [self._nodes[d] for d in task.depends_on]
                if any(d.status in _BLOCKING for d in deps):
                    target = TaskStatus.BLOCKED_ON_DEPENDENCY
                else:
                    target = TaskStatus.PENDING
                if target != task.status:
                    task.status = target
                    changed = True

    def ready_batch(self) -> List[StructuredTask]:
        """All PENDING tasks whose dependencies are COMPLETED — the next wave."""
        self.refresh_dependency_states()
        return [
            t for t in self._nodes.values()
            if t.status == TaskStatus.PENDING
            and all(self._nodes[d].status == TaskStatus.COMPLETED for d in t.depends_on)
        ]

    def is_terminal(self) -> bool:
        """True once nothing is running and nothing can start."""
        if any(t.status == TaskStatus.IN_PROGRESS for t in self._nodes.values()):
            return False
        return not self.ready_batch()

    def all_completed(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self._nodes.values())

    def pending_hitl(self) -> List[StructuredTask]:
        return [t for t in self._nodes.values() if t.status == TaskStatus.BLOCKED_ON_HITL]

    # -- Mutation -----------------------------------------------------------------
    def set_status(self, task_id: str, status: TaskStatus) -> None:
        self._nodes[task_id].status = status

    def approve_hitl(self, task_id: str) -> None:
        """BLOCKED_ON_HITL -> PENDING so the engine can dispatch it."""
        self.set_status(task_id, TaskStatus.PENDING)

    def reject_hitl(self, task_id: str) -> None:
        task = self._nodes[task_id]
        if task.status != TaskStatus.BLOCKED_ON_HITL:
            raise ValueError(f"Task '{task_id}' is not awaiting HITL confirmation")
        task.status = TaskStatus.FAILED

    def update_instruction(self, task_id: str, new_instruction: str) -> None:
        self._nodes[task_id].instruction = new_instruction
