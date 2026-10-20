"""
Base contract for all 7 Neefeel departmental executives.

Each call builds a fresh model agent (see llm.py), so a department never sees
another task's prompt unless it is passed in through the context block.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

from .. import llm
from ..models import Department, StructuredTask, TaskResult
from ..text_utils import OUTPUT_FORMAT_INSTRUCTIONS, infer_status_and_risks

MAX_FACT_CHARS_IN_PROMPT = 1500
MAX_UPSTREAM_CHARS_IN_PROMPT = 12000


def _clip(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


class BaseExecutive:
    department: Department
    system_prompt: str = "You are an executive department leader at Neefeel."

    def __init__(self, model_client: Any, project_root: str = "./neefeel_projects"):
        self.model_client = model_client
        self.project_root = project_root

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__.lower()

    async def _run_llm(self, prompt: str) -> str:
        return await llm.ask(
            self.model_client,
            name=self.agent_name,
            system_message=self.system_prompt + OUTPUT_FORMAT_INSTRUCTIONS,
            prompt=prompt,
            source="orchestrator",
        )

    def _run_dir(self, context: Dict[str, Any]) -> str:
        """project_root/<run_id>/ — run-scoped so T1 of run 2 never overwrites T1 of run 1."""
        run_id = (context or {}).get("run_id") or "adhoc"
        return os.path.abspath(os.path.join(self.project_root, str(run_id)))

    def _build_context_block(self, task: StructuredTask, context: Dict[str, Any]) -> str:
        global_facts = context.get("global") or []
        dept_facts = context.get("department_history") or []
        task_facts = context.get("task") or {}
        session_context = context.get("session_context", "")

        sections = []
        if global_facts:
            sections.append(
                "=== Company Identity (Global) ===\n"
                + "\n".join(f"- {_clip(f, MAX_FACT_CHARS_IN_PROMPT)}" for f in global_facts)
            )
        if dept_facts:
            sections.append(
                "=== This Department's Prior Work ===\n"
                + "\n".join(f"- {_clip(f, MAX_FACT_CHARS_IN_PROMPT)}" for f in dept_facts)
            )
        if task_facts:
            sections.append(
                "=== Upstream Dependency Output (work you must build on) ===\n"
                + "\n\n".join(f"[{k}]\n{_clip(v, MAX_UPSTREAM_CHARS_IN_PROMPT)}" for k, v in task_facts.items())
            )
        if session_context:
            sections.append(f"=== Session History ===\n{session_context}")
        sections.append(f"=== Task: {task.title} ===\n{task.instruction}")
        return "\n\n".join(sections)

    def _write_deliverable(self, task: StructuredTask, output: str, context: Dict[str, Any]) -> str:
        artifacts_dir = os.path.join(self._run_dir(context), "deliverables")
        os.makedirs(artifacts_dir, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", task.task_id)
        path = os.path.join(artifacts_dir, f"{safe_id}_deliverable.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Deliverable: {task.title}\n\n**Department:** {task.department.value}\n\n{output}")
        return path

    async def handle(self, task: StructuredTask, context: Dict[str, Any]) -> TaskResult:
        output = await self._run_llm(self._build_context_block(task, context))
        status, risks = infer_status_and_risks(output)
        deliverable_path = self._write_deliverable(task, output, context)
        return TaskResult(
            task_id=task.task_id,
            department=task.department,
            status=status,
            output=output,
            artifacts=[deliverable_path],
            risks=risks,
            data={},
        )
