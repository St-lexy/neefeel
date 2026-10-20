"""
DAG orchestration engine: parallel waves, selective HITL gating, Tier-3 memory
propagation, and per-task failure isolation.

Task lifecycle
--------------
PENDING -> (pre-run gate?) -> BLOCKED_ON_HITL --approve--> PENDING -> IN_PROGRESS
IN_PROGRESS -> COMPLETED
IN_PROGRESS -> BLOCKED_ON_HITL (executive emitted STATUS: blocked_on_hitl and the
               task had not been authorized up front). The finished result is HELD;
               approve ACCEPTS it (no re-run), modify re-runs with a new instruction.
IN_PROGRESS -> FAILED (handler raised, or founder rejected)
Dependents of anything blocked/failed show BLOCKED_ON_DEPENDENCY and resume
automatically once their dependencies complete.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from ..memory.scopes import CompanyMemory
from ..memory.session_state import SessionConversationManager
from ..models import Department, StructuredTask, TaskResult, TaskStatus
from ..safety.hitl import HITLGate
from .task_graph import TaskGraph

log = logging.getLogger(__name__)

ExecutiveHandler = Callable[[StructuredTask, Dict[str, Any]], Coroutine[Any, Any, TaskResult]]


class TaskOrchestrationEngine:
    def __init__(
        self,
        graph: TaskGraph,
        executives: Dict[Department, ExecutiveHandler],
        memory: CompanyMemory,
        hitl_gate: HITLGate,
        session_manager: Optional[SessionConversationManager] = None,
        run_id: Optional[str] = None,
    ):
        self.graph = graph
        self.executives = executives
        self.memory = memory
        self.hitl_gate = hitl_gate
        self.session_manager = session_manager
        self.run_id = run_id
        self.results: Dict[str, TaskResult] = {}
        self._held: Dict[str, TaskResult] = {}  # finished-but-awaiting-review results

    # -- helpers ----------------------------------------------------------------------
    def _get_task(self, task_id: str) -> Optional[StructuredTask]:
        return self.graph.tasks_by_id.get(task_id)

    def held_result(self, task_id: str) -> Optional[TaskResult]:
        return self._held.get(task_id)

    def _gate(self, task: StructuredTask) -> None:
        self.graph.set_status(task.task_id, TaskStatus.BLOCKED_ON_HITL)
        self.results[task.task_id] = TaskResult(
            task_id=task.task_id,
            department=task.department,
            status="blocked_on_hitl",
            output=f"'{task.title}' requires founder authorization before it runs.",
            risks=["Gated by HITL policy before execution"],
            data={"gate": "pre_execution"},
        )

    def _fail(self, task: StructuredTask, reason: str) -> TaskResult:
        self.graph.set_status(task.task_id, TaskStatus.FAILED)
        result = TaskResult(
            task_id=task.task_id,
            department=task.department,
            status="failed",
            output=reason,
            risks=[reason],
            data={"gate": "none"},
        )
        self.results[task.task_id] = result
        return result

    async def _after_completion(self, task: StructuredTask, result: TaskResult) -> None:
        """Memory bookkeeping must never fail a task that already succeeded."""
        try:
            await self.memory.record_result_as_department_fact(task, result.output, self.run_id)
        except Exception:
            log.exception("Could not record department fact for %s", task.task_id)
        for dependent in self.graph.tasks:
            if task.task_id in dependent.depends_on:
                label = f"{task.task_id} · {task.department.value} · {task.title}"
                try:
                    self.memory.pass_upstream_output(task.task_id, dependent.task_id, result.output, label)
                except Exception:
                    log.exception("Could not pass %s output to %s", task.task_id, dependent.task_id)

    async def _complete(self, task: StructuredTask, result: TaskResult) -> TaskResult:
        result.status = "completed"
        self.graph.set_status(task.task_id, TaskStatus.COMPLETED)
        self.results[task.task_id] = result
        await self._after_completion(task, result)
        return result

    # -- dispatch -----------------------------------------------------------------------
    async def _dispatch_one(self, task: StructuredTask) -> TaskResult:
        """Runs one task. Never raises: a failing executive fails only its own task."""
        self.graph.set_status(task.task_id, TaskStatus.IN_PROGRESS)
        try:
            context = await self.memory.build_context_for_task(task)
            if self.session_manager:
                context["session_context"] = self.session_manager.get_conversation_context()
            context["run_id"] = self.run_id
            result = await self.executives[task.department](task, context)
        except Exception as exc:
            log.exception("Task %s failed", task.task_id)
            return self._fail(task, f"{type(exc).__name__}: {exc}")

        if result.status == "failed":
            self.graph.set_status(task.task_id, TaskStatus.FAILED)
            self.results[task.task_id] = result
            return result

        if result.status == "blocked_on_hitl" and not self.hitl_gate.is_approved(task.task_id):
            # Post-run review: keep the real output, wait for the founder.
            result.data = {**(result.data or {}), "gate": "post_execution"}
            self._held[task.task_id] = result
            self.results[task.task_id] = result
            self.graph.set_status(task.task_id, TaskStatus.BLOCKED_ON_HITL)
            return result

        return await self._complete(task, result)

    async def run(self) -> List[TaskResult]:
        """Runs ready tasks wave by wave. Gated tasks pause without stalling
        unblocked siblings. Safe to call again after approvals."""
        while True:
            ready = self.graph.ready_batch()
            if not ready:
                break
            runnable = []
            for task in ready:
                if self.hitl_gate.should_gate_now(task):
                    self._gate(task)
                else:
                    runnable.append(task)
            if runnable:
                await asyncio.gather(*(self._dispatch_one(t) for t in runnable))
        return list(self.results.values())

    # -- founder decisions ----------------------------------------------------------------
    async def approve_multiple(self, task_ids: List[str]) -> List[TaskResult]:
        """Authorizes tasks, then advances the graph with ONE run() so
        dependency order and parallelism are respected."""
        for tid in task_ids:
            task = self._get_task(tid)
            if task is None or task.status in (
                TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS, TaskStatus.FAILED
            ):
                continue
            self.hitl_gate.approve(tid)
            held = self._held.pop(tid, None)
            if held is not None:
                await self._complete(task, held)  # accept reviewed output, no re-run
            elif task.status == TaskStatus.BLOCKED_ON_HITL:
                self.graph.approve_hitl(tid)
        await self.run()
        return list(self.results.values())

    async def resume_after_approval(self, task_id: str) -> List[TaskResult]:
        return await self.approve_multiple([task_id])

    async def reject(self, task_id: str, reason: str = "") -> TaskResult:
        task = self._get_task(task_id)
        dept = task.department if task else Department.ENGINEERING
        held = self._held.pop(task_id, None)
        if task is not None:
            self.graph.set_status(task_id, TaskStatus.FAILED)
        result = TaskResult(
            task_id=task_id,
            department=dept,
            status="failed",
            output=f"Rejected by founder. Reason: {reason or 'none given'}",
            data={"gate": "none", **({"rejected_output": held.output} if held else {})},
        )
        self.results[task_id] = result
        self.graph.refresh_dependency_states()
        return result

    async def modify_and_resume(self, task_id: str, new_instruction: str) -> List[TaskResult]:
        """Founder edits the instruction and re-runs the task (authorized)."""
        task = self._get_task(task_id)
        if task is None or task.status != TaskStatus.BLOCKED_ON_HITL:
            return list(self.results.values())
        task.instruction = new_instruction
        self._held.pop(task_id, None)
        self.hitl_gate.approve(task_id)
        self.graph.approve_hitl(task_id)
        await self.run()
        return list(self.results.values())
