"""
Tier 1: The AI Co-founder.
Multi-turn dialogue -> identify missing context -> decompose into a task DAG ->
mobilize the executive pod -> synthesize one founder-facing briefing.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()

import json

from autogen_core.models import ModelInfo
from autogen_ext.models.openai import OpenAIChatCompletionClient

from . import llm
from .executives.base import BaseExecutive
from .executives.design import DesignExecutive
from .executives.engineering import EngineeringExecutive
from .executives.finance import FinanceExecutive
from .executives.growth import GrowthExecutive
from .executives.legal import LegalExecutive
from .executives.people import PeopleExecutive
from .executives.product import ProductExecutive
from .memory.embeddings import DeterministicHashEmbedding
from .memory.persistent_store import InMemoryPersistentStore, PersistentMemoryStore
from .memory.scopes import CompanyMemory
from .memory.session_state import SessionConversationManager
from .models import (
    CofounderDialogueResponse,
    DecompositionPlan,
    Department,
    ExecutiveBriefing,
    TaskResult,
    TaskStatus,
)
from .orchestration.engine import TaskOrchestrationEngine
from .orchestration.task_graph import TaskGraph
from .safety.conflict import ConflictResolver
from .safety.hitl import HITLGate
from .text_utils import strip_think

DIALOGUE_SYSTEM_PROMPT = """You are the AI Co-founder of Neefeel.
You speak with sharp, operational clarity, acting as a real partner rather than a generic assistant.
You lead an executive team: Product, Design, Engineering and Growth are always available;
Legal, Finance and People are brought in when the venture needs them.

Your core objectives:
1. Interrogate and challenge weak business or technical assumptions.
2. Identify missing variables and trade-offs.
3. Recall past conversation history and build upon earlier decisions.
4. Signal readiness with "intent":
   - "conversational_inquiry": open-ended brainstorming, or the idea is still too vague to plan.
   - "ready_for_execution": the founder has given enough to start (what is being built, for whom,
     rough stack/constraints, monetization) OR explicitly tells you to mobilize/build/go ahead.
     Details the departments can decide or draft themselves do NOT block execution: list them
     in "missing_information" and proceed anyway.
   - CRITICAL: never withhold execution to demand legal sign-off, signed banking agreements, or
     completed customer discovery. The team's job is to DRAFT those legal disclaimers, fee models
     and architecture specs.
5. When intent is "ready_for_execution", write "execution_brief": a complete, self-contained
   directive (the venture, target users, market, stack, monetization, constraints, and every
   decision agreed earlier in this conversation). The planning engine sees ONLY this brief plus the
   transcript, so never write "as discussed" or "go ahead". Otherwise use "".

Output strictly valid JSON matching this schema:
{
  "intent": "conversational_inquiry | ready_for_execution",
  "reply": "Your candid co-founder analysis (escape newlines as \\n)",
  "missing_information": ["missing point 1"],
  "recalled_facts": ["fact recalled from previous turns"],
  "execution_brief": ""
}
Do NOT output markdown code fences or <think> tags. Return pure JSON only.
"""

DECOMPOSITION_SYSTEM_PROMPT = """You are the AI Co-founder's intent-decomposition engine for Neefeel.
Split one founder directive into a DAG of tasks across our 7 departments:
Core: product, design, engineering, growth
On-demand: legal, finance, people

Rules:
1. task_id: "T1", "T2", ... unique and sequential.
2. Always plan the core departments that the directive needs. Add on-demand departments ONLY when
   implied: legal (terms/privacy/contracts/compliance/regulated data/payments), finance (pricing,
   monetization, unit economics, runway, payment-fee impact), people (hiring, team, contractors).
3. depends_on = task_ids whose OUTPUT is an input to this task and must COMPLETE first. Independent
   work must not depend on each other (it runs in parallel). Typical edges: design -> product;
   engineering -> product (and design when there is a UI); finance -> product; people -> finance;
   legal -> product (and finance when pricing/payments matter); growth -> product. Executives see
   only their instruction, their upstream outputs and company memory, so wire dependencies
   wherever one department must build on another. No cycles; reference only existing task_ids.
4. instruction: self-contained, imperative, 2-5 sentences stating exactly what to produce and any
   constraints. Start text deliverables with a drafting verb (Draft, Write, Design, Model, Plan,
   Define). Use action verbs (deploy, publish, charge, send, sign, delete) ONLY if the task must
   really perform that live action.
5. requires_human_confirmation: true only for tasks that PERFORM or COMMIT to real-world action
   (live deployment, real spend, mail to real customers, signing/binding contracts). Drafting,
   planning and modeling are false. (Legal tasks are gated automatically.)
6. risk_level: low | medium | high = blast radius if the output were acted on unreviewed.
7. should_build: true on the single engineering task that must produce a runnable browser
   prototype; false on every other task. Never fold deployment into that task: if the directive
   mentions deploying/publishing, make it a SEPARATE engineering task that depends on the build task
   (it will be held for founder approval; the prototype itself must not wait for it).
8. Produce 4-9 tasks.

Output strictly valid JSON matching this schema:
{
  "founder_prompt": "...",
  "summary": "...",
  "tasks": [
    {
      "task_id": "T1",
      "department": "product | design | engineering | growth | legal | finance | people",
      "title": "...",
      "instruction": "...",
      "depends_on": [],
      "requires_human_confirmation": false,
      "risk_level": "low | medium | high",
      "should_build": false
    }
  ]
}
Do NOT output markdown code fences or <think> tags. Return pure JSON only.
"""

SYNTHESIS_SYSTEM_PROMPT = """You are the Neefeel executive-briefing synthesizer.
You receive: the founder's prompt, the plan summary, every task's status, the head of each task's
output, the risks each executive reported, surfaced conflicts, and pending founder confirmations.
Compile ONE founder-facing briefing. Use only facts present in the input; do not invent results.
Mention tasks that are blocked, failed or never ran, and why. Every pending confirmation must
appear in next_actions as a concrete decision for the founder.

Output strictly valid JSON matching this schema (deliverables are attached by the system, do not list them):
{
  "strategy_summary": "High-level briefing and verdict in markdown (escape newlines as \\n)",
  "risks": ["Consolidated, de-duplicated risk 1"],
  "conflicts": ["Surfaced conflict 1"],
  "next_actions": ["Next action 1"]
}
Do NOT output markdown code fences or <think> tags. Return pure JSON only.
"""

_BUILDISH_RE = re.compile(
    r"\b(prototype|build|implement|mvp|front-?end|ui|portal|dashboard|app|web|html|page|site)\b", re.IGNORECASE
)


def ensure_build_task(plan: DecompositionPlan) -> Optional[str]:
    """Guarantees the plan can produce a web preview. Planner models often omit
    `should_build`; without it nothing is built and the founder sees no preview.
    If no engineering task is flagged to build, the best-matching one is (preferring
    a task that is not a deployment step). Every other unflagged engineering task is
    set to False. Returns the id of the build task, or None if the plan has no
    engineering task or the planner explicitly disabled every one."""
    eng = [t for t in plan.tasks if t.department == Department.ENGINEERING]
    flagged = [t for t in eng if t.should_build is True]
    if not flagged:
        if not eng or all(t.should_build is False for t in eng):
            return None
        def score(t):
            text = f"{t.title} {t.instruction}"
            deploy_only = bool(re.match(r"(?i)^\W*(deploy|publish|release|ship)\b", t.instruction or t.title))
            return (not deploy_only, len(_BUILDISH_RE.findall(text)))
        candidates = [t for t in eng if t.should_build is None]
        best = max(candidates, key=lambda t: (score(t), -plan.tasks.index(t)))
        best.should_build = True
        flagged = [best]
    for t in eng:
        if t.should_build is None:
            t.should_build = False
    return flagged[0].task_id


ModelEndpoint = Tuple[str, str]  # (api_key, base_url)


def _resolve_endpoint(api_key: Optional[str], base_url: Optional[str]) -> ModelEndpoint:
    """Keeps each API key paired with ITS OWN base URL, so one provider's key is
    never sent to another provider's host."""
    env = os.environ.get
    fireworks_url = env("FIREWORKS_BASE_URL") or "https://api.fireworks.ai/inference/v1"
    if api_key:  # explicit key: explicit URL, else Fireworks (the project default)
        return api_key, base_url or fireworks_url
    if env("FIREWORKS_API_KEY"):
        return env("FIREWORKS_API_KEY"), base_url or fireworks_url
    if env("CEREBRAS_API_KEY"):
        return env("CEREBRAS_API_KEY"), base_url or env("CEREBRAS_BASE_URL") or "https://api.cerebras.ai/v1"
    if env("OPENAI_API_KEY"):
        return env("OPENAI_API_KEY"), base_url or "https://api.openai.com/v1"
    return "lm-studio", base_url or env("LOCAL_BASE_URL") or "http://localhost:1234/v1"


def _one_line_summary(output: str, limit: int = 160) -> str:
    """First meaningful prose line of a deliverable, without markdown noise or the Risks footer."""
    for line in strip_think(output).splitlines():
        clean = re.sub(r"[#*_`>|]+", "", line).strip(" -\t")
        if not clean or re.match(r"(?i)^(risks?|status)\s*:", clean):
            continue
        return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"
    return "(no content)"


class AICofounder:
    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        persistent_store: Optional[PersistentMemoryStore] = None,
        project_root: str = "./neefeel_projects",
        auto_open_preview: bool = False,
    ):
        resolved_api_key, resolved_base_url = _resolve_endpoint(api_key, base_url)
        resolved_model = (
            model
            or os.environ.get("NEELFEEL_MODEL")
            or "accounts/fireworks/models/deepseek-v4-pro-0813"
        )

        model_info = ModelInfo(
            vision=False, function_calling=False, json_output=True,
            family="unknown", structured_output=False,
        )
        # Explicit output budgets. Providers apply a small default max_tokens (some as low as
        # ~2k), which silently truncates long documents and — fatally — whole prototypes.
        # Reasoning models also spend part of the budget on thinking.
        self._model_client = OpenAIChatCompletionClient(
            model=resolved_model, base_url=resolved_base_url, api_key=resolved_api_key,
            model_info=model_info, max_tokens=int(os.environ.get("NEELFEEL_MAX_TOKENS", "8000")),
        )
        self._builder_client = OpenAIChatCompletionClient(
            model=resolved_model, base_url=resolved_base_url, api_key=resolved_api_key,
            model_info=model_info, max_tokens=int(os.environ.get("NEELFEEL_BUILDER_MAX_TOKENS", "24000")),
        )
        self.project_root = project_root

        self.session_manager = SessionConversationManager(max_history_turns=12)
        self.memory = CompanyMemory(
            persistent_store or InMemoryPersistentStore(DeterministicHashEmbedding())
        )
        self.hitl_gate = HITLGate()
        self._conflict_resolver = ConflictResolver(self._model_client)

        # 7-seat executive pod. Every seat shares project_root so deliverables
        # and prototypes land in the same run-scoped tree.
        self._executives: Dict[Department, BaseExecutive] = {
            Department.PRODUCT: ProductExecutive(self._model_client, project_root),
            Department.DESIGN: DesignExecutive(self._model_client, project_root),
            Department.ENGINEERING: EngineeringExecutive(
                self._model_client, project_root, auto_open_preview, builder_client=self._builder_client
            ),
            Department.GROWTH: GrowthExecutive(self._model_client, project_root),
            Department.LEGAL: LegalExecutive(self._model_client, project_root),
            Department.FINANCE: FinanceExecutive(self._model_client, project_root),
            Department.PEOPLE: PeopleExecutive(self._model_client, project_root),
        }

        self._active_graph: Optional[TaskGraph] = None
        self._active_engine: Optional[TaskOrchestrationEngine] = None
        self._active_run_id: Optional[str] = None
        self._recorded_turns: Set[Tuple[str, str]] = set()

    # -- Dialogue --------------------------------------------------------------------------
    async def chat(self, user_message: str) -> CofounderDialogueResponse:
        session_history = self.session_manager.get_conversation_context()
        company_records = await self.memory.query_all_scopes(user_message, top_k=3)
        company_facts = (
            "\n".join(f"- {r.get('content', '')[:600]}" for r in company_records)
            if company_records else "None."
        )
        full_prompt = (
            f"=== Long-Term Company Facts ===\n{company_facts}\n\n"
            f"=== Session Conversation History ===\n{session_history}\n\n"
            f"=== Founder Message ===\n{user_message}"
        )

        try:
            parsed = await llm.ask_json(
                self._model_client, name="cofounder_dialogue",
                system_message=DIALOGUE_SYSTEM_PROMPT, prompt=full_prompt, source="founder",
                validate=CofounderDialogueResponse.model_validate,
            )
        except llm.LLMJSONError as exc:
            # The model answered but not in JSON: show its text rather than crash the chat.
            parsed = CofounderDialogueResponse(
                intent="conversational_inquiry",
                reply=strip_think(exc.raw) or "I could not formulate a response — please rephrase.",
            )

        self.session_manager.add_turn(role="founder", content=user_message)
        self.session_manager.add_turn(
            role="cofounder", content=parsed.reply, artifacts=[f"intent:{parsed.intent}"]
        )
        return parsed

    # -- Planning --------------------------------------------------------------------------
    async def decompose(self, founder_prompt: str) -> DecompositionPlan:
        """Plans are validated as a real DAG (unique ids, known dependencies, no
        cycles) inside the repair loop, so the model gets one chance to fix a bad
        plan instead of the run crashing later."""
        session_ctx = self.session_manager.get_conversation_context()
        full_prompt = f"{session_ctx}\n\nFounder Intent for Execution:\n{founder_prompt}"

        def _validate(data: dict) -> DecompositionPlan:
            plan = DecompositionPlan.model_validate(data)
            TaskGraph(plan.tasks)  # raises on duplicates / unknown deps / cycles
            return plan

        plan = await llm.ask_json(
            self._model_client, name="intent_decomposer",
            system_message=DECOMPOSITION_SYSTEM_PROMPT, prompt=full_prompt,
            source="founder", validate=_validate,
        )
        plan.founder_prompt = founder_prompt
        ensure_build_task(plan)
        return plan

    # -- Execution -------------------------------------------------------------------------
    def _new_run_id(self) -> str:
        return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"

    async def _run_pipeline(self, plan: DecompositionPlan) -> List[TaskResult]:
        # Work on private copies: the graph mutates task status and gate flags, and
        # the same plan must stay re-runnable (and unchanged) afterwards.
        graph = TaskGraph([
            t.model_copy(deep=True, update={"status": TaskStatus.PENDING}) for t in plan.tasks
        ])
        self.hitl_gate = HITLGate()  # approvals belong to one run, not to the process
        self.hitl_gate.apply(graph)
        self.memory.reset_task_context()

        run_id = self._new_run_id()
        engine = TaskOrchestrationEngine(
            graph=graph,
            executives={dept: exe.handle for dept, exe in self._executives.items()},
            memory=self.memory,
            hitl_gate=self.hitl_gate,
            session_manager=self.session_manager,
            run_id=run_id,
        )
        self._active_graph, self._active_engine, self._active_run_id = graph, engine, run_id

        results = await engine.run()
        self._sync_session(results)
        return results

    execute = _run_pipeline  # public name

    def current_results(self) -> List[TaskResult]:
        """The latest result per task (one entry per task_id)."""
        return list(self._active_engine.results.values()) if self._active_engine else []

    def _sync_session(self, results: List[TaskResult]) -> None:
        """Records each completed executive output in the session once."""
        for r in results:
            key = (self._active_run_id or "", r.task_id)
            if r.status == "completed" and key not in self._recorded_turns:
                self._recorded_turns.add(key)
                self.session_manager.add_turn(
                    role="executive", content=r.output[:500],
                    department=r.department.value, task_id=r.task_id, artifacts=r.artifacts,
                )

    def _require_engine(self) -> TaskOrchestrationEngine:
        if self._active_engine is None:
            raise RuntimeError("No active run. Call decompose() and execute() first.")
        return self._active_engine

    async def approve(self, task_id: str) -> List[TaskResult]:
        results = await self._require_engine().resume_after_approval(task_id)
        self._sync_session(results)
        return results

    async def approve_all(self, task_ids: List[str]) -> List[TaskResult]:
        results = await self._require_engine().approve_multiple(task_ids)
        self._sync_session(results)
        return results

    async def reject(self, task_id: str, reason: str = "") -> TaskResult:
        return await self._require_engine().reject(task_id, reason)

    async def modify_and_resume(self, task_id: str, new_instruction: str) -> List[TaskResult]:
        results = await self._require_engine().modify_and_resume(task_id, new_instruction)
        self._sync_session(results)
        return results

    async def rebuild_prototype(self, task_id: str) -> TaskResult:
        """Retries ONLY the prototype build for an engineering task (e.g. after a
        truncated/unparseable model reply), reusing its finished architecture text."""
        engine = self._require_engine()
        task, result = engine._get_task(task_id), engine.results.get(task_id)
        if task is None or result is None or task.department != Department.ENGINEERING:
            raise ValueError(f"'{task_id}' is not a finished engineering task")
        exe = self._executives[Department.ENGINEERING]
        await exe.build_prototype(task, result, {"run_id": self._active_run_id})
        return result

    # -- Synthesis -------------------------------------------------------------------------
    async def synthesize(
        self,
        founder_prompt: str,
        plan: DecompositionPlan,
        results: Optional[List[TaskResult]] = None,
    ) -> ExecutiveBriefing:
        """`results` defaults to the engine's latest results. Whatever is passed is
        collapsed to ONE entry per task_id, keeping the LAST (most recent) one."""
        latest: Dict[str, TaskResult] = {}
        for r in (results if results is not None else self.current_results()):
            latest[r.task_id] = r
        # Live task state lives in the active graph (the plan holds the original copies).
        tasks = self._active_graph.tasks_by_id if self._active_graph else {t.task_id: t for t in plan.tasks}

        conflicts = await self._conflict_resolver.detect_and_resolve(tasks, latest)
        conflict_strings = [f"[{c.summary}] Resolution: {c.resolution_proposal}" for c in conflicts]

        pending = self.hitl_gate.pending_confirmations(self._active_graph) if self._active_graph else []

        preview_url = None
        for r in latest.values():
            preview = (r.data or {}).get("preview")
            if preview and preview.get("index_path"):
                preview_url = preview["index_path"]

        deliverables: List[str] = []
        all_risks: List[str] = []
        for tid, r in latest.items():
            title = tasks[tid].title if tid in tasks else tid
            dept = r.department.value
            if r.status == "completed":
                files = f" [{len(r.artifacts)} file(s)]" if r.artifacts else ""
                deliverables.append(f"{tid} ({dept}) — {title}: {_one_line_summary(r.output)}{files}")
            elif r.status == "blocked_on_hitl":
                deliverables.append(f"{tid} ({dept}) — {title}: awaiting founder approval")
            else:
                deliverables.append(f"{tid} ({dept}) — {title}: {r.status}")
            for risk in r.risks:
                if risk not in all_risks:
                    all_risks.append(risk)

        task_status = {tid: t.status.value for tid, t in tasks.items()}
        payload = {
            "founder_prompt": founder_prompt,
            "plan_summary": plan.summary,
            "task_status": task_status,
            "results": [
                {
                    "task_id": r.task_id,
                    "title": tasks[r.task_id].title if r.task_id in tasks else r.task_id,
                    "department": r.department.value,
                    "status": r.status,
                    "output_head": r.output[:700],
                    "risks": r.risks,
                }
                for r in latest.values()
            ],
            "conflicts": conflict_strings,
            "pending_confirmations": pending,
        }

        try:
            briefing = await llm.ask_json(
                self._model_client, name="executive_synthesizer",
                system_message=SYNTHESIS_SYSTEM_PROMPT,
                prompt=json.dumps(payload, indent=2), source="system",
                validate=ExecutiveBriefing.model_validate,
            )
        except (llm.LLMJSONError, RuntimeError) as exc:
            lines = [f"- {tid}: {status}" for tid, status in task_status.items()]
            briefing = ExecutiveBriefing(
                strategy_summary=(
                    "Automatic briefing unavailable "
                    f"({type(exc).__name__}). Task status:\n" + "\n".join(lines)
                    + (f"\n\nModel's raw reply:\n{strip_think(getattr(exc, 'raw', ''))}" if getattr(exc, "raw", "") else "")
                ),
            )

        # Facts the system knows better than the model are authoritative.
        briefing.deliverables = deliverables
        if not briefing.risks:
            briefing.risks = all_risks
        if not briefing.conflicts:
            briefing.conflicts = conflict_strings
        for title in pending:
            if not any(title in a for a in briefing.next_actions):
                briefing.next_actions.append(f"Founder decision needed: approve or reject '{title}'")
        briefing.pending_confirmations = pending
        briefing.preview_url = preview_url
        return briefing

    async def run(self, founder_prompt: str) -> ExecutiveBriefing:
        plan = await self.decompose(founder_prompt)
        await self.execute(plan)
        return await self.synthesize(founder_prompt, plan)

    def reset_session(self) -> None:
        """Forget the conversation and any active run (long-term memory is kept)."""
        self.session_manager.clear()
        self.memory.reset_task_context()
        self.hitl_gate = HITLGate()
        self._active_graph = self._active_engine = self._active_run_id = None
        self._recorded_turns.clear()

    async def close(self) -> None:
        await self._model_client.close()
        await self._builder_client.close()
