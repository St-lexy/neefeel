"""
Engineering Executive Office.

Writes architecture/schema/API documents like every other department (via the
shared BaseExecutive.handle, so risks and STATUS signals are honoured), and —
when the task is flagged to build — hands the spec to the CodeBuilderEngine and
writes a sanitized prototype to disk.
"""

from __future__ import annotations

import html
import os
import re
from typing import Any, Dict

from ..builder.code_builder import CodeBuilderEngine
from ..builder.preview import write_project_and_preview
from ..models import StructuredTask, TaskResult
from .base import BaseExecutive

# Whole-word only. (The old substring check matched "ui" inside "requirements"
# and "app" inside "approach", so nearly every task triggered a full build.)
_BUILD_RE = re.compile(
    r"\b(prototype|scaffold|front-?end|html|landing page|web ?app|mock-?up|clickable|interactive demo|build|implement|mvp)\b",
    re.IGNORECASE,
)
_HTML_BLOCK_RE = re.compile(r"```html\s*\n(?P<body>.*?)```", re.DOTALL | re.IGNORECASE)


class EngineeringExecutive(BaseExecutive):
    system_prompt = """You are the AI Chief Technology Officer at Neefeel. You own:
- system architecture, data model / database schema, API contracts
- technical feasibility of what Product and Design have specified
- the plan for a clean, single-page, browser-runnable prototype

Rules:
- Write the architecture, schema and API contract directly in your response. Do NOT paste
  full source files here — when this task is flagged to build, the prototype is generated
  separately by the builder from your response.
- Review the upstream Product/Design output for feasibility. If something is not realistic
  for an MVP, say so plainly and, in your Risks section, write a line starting with the
  exact phrase "contradicts Product's scope:" followed by why and a cheaper alternative —
  that phrasing is what triggers cross-departmental conflict resolution, so don't
  paraphrase it away.
- Payments, deployment and third-party calls in the prototype are SIMULATED; never ask for
  real credentials. Anything that would need a real deployment or spend belongs in Risks.
"""

    def __init__(self, model_client: Any, project_root: str = "./neefeel_projects",
                 auto_open_preview: bool = False, builder_client: Any = None):
        super().__init__(model_client, project_root)
        self.auto_open_preview = auto_open_preview
        # A prototype needs a far larger output budget than a document; the builder may
        # use its own client configured for that.
        self.builder = CodeBuilderEngine(builder_client or model_client)

    @staticmethod
    def wants_build(task: StructuredTask) -> bool:
        """The decomposer's explicit `should_build` wins; otherwise a whole-word heuristic."""
        if task.should_build is not None:
            return bool(task.should_build)
        return bool(_BUILD_RE.search(f"{task.title} {task.instruction}"))

    async def handle(self, task: StructuredTask, context: Dict[str, Any]) -> TaskResult:
        result = await super().handle(task, context)  # real status, risks and deliverable file
        if self.wants_build(task):
            await self.build_prototype(task, result, context)
        return result

    async def build_prototype(self, task: StructuredTask, result: TaskResult, context: Dict[str, Any]) -> bool:
        """Generates and writes the prototype, updating `result` in place
        (artifacts, data['preview'] or data['build_error'] + a risk). Returns success.
        Also used to retry a failed build without re-running the whole task."""
        run_dir = self._run_dir(context)
        safe_id = re.sub(r"[^a-z0-9_-]", "", task.task_id.lower()) or "task"
        spec = (
            f"{task.title}\n{task.instruction}\n\n"
            f"Technical Architecture (from the CTO):\n{result.output}"
        )
        # a retry replaces the previous failure
        result.risks = [r for r in result.risks if not r.startswith("Prototype build failed")]
        result.data.pop("build_error", None)
        try:
            project = await self.builder.generate(spec)
            project.project_name = f"{safe_id}-{project.project_name}"
            info = write_project_and_preview(project, run_dir, auto_open=self.auto_open_preview)
            for f in info.files:
                if f not in result.artifacts:
                    result.artifacts.append(f)
            result.data["preview"] = {
                "project_dir": info.project_dir,
                "index_path": info.index_path,
                "opened": info.opened,
            }
            return True
        except Exception as exc:
            result.risks.append(f"Prototype build failed: {exc}")
            result.data["build_error"] = str(exc)

        # Last resort: the CTO's own response contained a complete HTML page.
        m = _HTML_BLOCK_RE.search(result.output)
        if m and "<html" in m.group("body").lower():
            proj_dir = os.path.join(run_dir, f"{safe_id}-fallback")
            os.makedirs(proj_dir, exist_ok=True)
            index_path = os.path.join(proj_dir, "index.html")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(m.group("body").strip())
            result.artifacts.append(index_path)
            result.data["preview"] = {"project_dir": proj_dir, "index_path": index_path, "opened": False}
            return True
        return False
