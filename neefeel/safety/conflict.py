"""
Phase 5: Cross-departmental conflict resolution.

Detection: a completed task whose Risks contain feasibility/conflict language
(executives are told to write e.g. "contradicts Product's pricing:"; see
FEASIBILITY_RISK_KEYWORDS and text_utils.infer_status_and_risks).
Resolution: an LLM compares the flagged task with the upstream task(s) it
depends on — preferring the department the risk names — and proposes a
resolution plus alternatives. If the model call or its JSON fails, a report
built from the executive's own risk text is returned instead of a generic
placeholder, so a conflict is never silently dropped.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import llm
from ..models import ConflictReport, Department, StructuredTask, TaskResult

FEASIBILITY_RISK_KEYWORDS = [
    "infeasible", "not feasible", "unfeasible", "out of scope for mvp", "not realistic",
    "contradicts",
]

MAX_SOURCE_CHARS = 3000

CONFLICT_SYSTEM_PROMPT = """You are the Neefeel Co-founder's conflict-resolution module.
You are given the flagged task's output and risks, plus the upstream output(s) it conflicts with.
Analyze the trade-off and produce a resolution plus real alternatives.

Do NOT output <think> tags or commentary. Output ONLY valid JSON matching this exact schema:
{
  "description": "what the conflict actually is, in one or two sentences",
  "recommended_resolution": "your recommended path forward",
  "alternatives": ["alternative 1", "alternative 2"]
}
"""


class ConflictResolver:
    def __init__(self, model_client: Any):
        self._model_client = model_client

    @staticmethod
    def _find_conflict_flags(results: Dict[str, TaskResult]) -> List[TaskResult]:
        flagged = []
        for result in results.values():
            if result.status != "completed":
                continue
            risks = result.risks or []
            if any(any(kw in r.lower() for kw in FEASIBILITY_RISK_KEYWORDS) for r in risks):
                flagged.append(result)
        return flagged

    @staticmethod
    def _pick_sources(
        flagged_task: StructuredTask, tasks: Dict[str, StructuredTask], risk_text: str
    ) -> List[StructuredTask]:
        """Upstream tasks this conflict is about: the ones whose department the
        risk names ("contradicts Product's pricing"), otherwise all dependencies."""
        deps = [tasks[d] for d in flagged_task.depends_on if d in tasks]
        named = [d for d in deps if d.department.value in risk_text.lower()]
        return named or deps

    async def detect_and_resolve(
        self, tasks: Dict[str, StructuredTask], results: Dict[str, TaskResult]
    ) -> List[ConflictReport]:
        reports: List[ConflictReport] = []
        for flagged_result in self._find_conflict_flags(results):
            flagged_task = tasks.get(flagged_result.task_id)
            if flagged_task is None:
                continue

            conflict_risks = [
                r for r in flagged_result.risks
                if any(kw in r.lower() for kw in FEASIBILITY_RISK_KEYWORDS)
            ]
            risk_text = "; ".join(conflict_risks)
            sources = [
                s for s in self._pick_sources(flagged_task, tasks, risk_text)
                if s.task_id in results and results[s.task_id].status == "completed"
            ]

            dept_b = flagged_task.department
            task_ids = [s.task_id for s in sources] + [flagged_result.task_id]
            departments: List[Department] = [s.department for s in sources] + [dept_b]

            upstream_block = "\n\n".join(
                f"[Upstream {s.department.value}, id={s.task_id}]\n{results[s.task_id].output[:MAX_SOURCE_CHARS]}"
                for s in sources
            ) or "(no upstream task is recorded for this conflict)"
            prompt = (
                f"{upstream_block}\n\n"
                f"[Flagged task {dept_b.value}, id={flagged_result.task_id}]\n"
                f"{flagged_result.output[:MAX_SOURCE_CHARS]}\n\n"
                f"Conflict risks cited by {dept_b.value}: {risk_text}"
            )

            try:
                data = await llm.ask_json(
                    self._model_client, name="conflict_resolver",
                    system_message=CONFLICT_SYSTEM_PROMPT, prompt=prompt, source="cofounder",
                )
                summary = str(data.get("description") or risk_text)
                resolution = str(data.get("recommended_resolution") or "Align cross-functional requirements.")
                alts = data.get("alternatives") or []
                if alts:
                    resolution += " | Alternatives: " + "; ".join(str(a) for a in alts)
            except Exception:
                summary = risk_text or f"Conflict flagged by {dept_b.value}."
                resolution = "Automatic resolution unavailable — review the flagged deliverable and its upstream task directly."

            reports.append(ConflictReport(
                task_ids=task_ids, departments=departments,
                summary=summary, resolution_proposal=resolution,
            ))
        return reports
