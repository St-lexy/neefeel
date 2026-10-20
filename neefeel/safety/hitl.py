"""
Phase 5: Human-In-The-Loop confirmation gate.

Two independent mechanisms exist, and they mean different things:

  1. PRE-RUN gate (this module): "do not start this task until the founder
     authorizes it." Set by (a) the decomposer's `requires_human_confirmation`,
     (b) unconditional policy for every Legal task, and (c) the deterministic
     scan below.
  2. POST-RUN review (executives emit `STATUS: blocked_on_hitl`): "the draft is
     done but must be reviewed before anything consumes it." The engine holds
     that result and approving it ACCEPTS the existing output — it never re-runs
     the task. A task that was already authorized up front is not asked twice.

The keyword scan gates tasks that PERFORM or COMMIT to a real-world action
(live deploy, real spend, mail to real customers, signing contracts, deletions).
Tasks whose job is to draft, design, model or plan produce text only and are
not gated just because the topic is money or launches — nothing in this
platform actually deploys or pays.
"""

from __future__ import annotations

import re
from typing import List

from ..models import Department, StructuredTask
from ..orchestration.task_graph import TaskGraph

# Instruction starts with a verb that produces a document, not an action.
_DRAFTING_LEAD_RE = re.compile(
    r"^\W*(?:draft|write|design|model|plan|outline|analy[sz]e|document|specify|define|"
    r"estimate|evaluate|research|compare|review|prepare|propose|produce|summari[sz]e|"
    r"list|describe|map|identify|recommend|benchmark|assess|create (?:a |an |the )?"
    r"(?:spec|plan|prd|draft|model|outline|persona|wireframe|roadmap|strategy|schema|architecture))\b"
)

# Explicit "do it for real" language beats the drafting exemption.
_EXPLICIT_EXECUTION_RE = re.compile(
    r"\bgo(?:es|ing)? live\b"
    r"|\b(?:actually|for real|immediately)\b.{0,25}\b(?:deploy|publish|charge|send|pay|launch|delete)\b"
    r"|\bexecute (?:the )?(?:payment|transfer|deployment|contract)\b"
)

_ACTION_PATTERNS = [
    r"\b(?:deploy|publish|release|ship|push|promote)\b.{0,40}\b(?:to|on)\b.{0,25}"
    r"\b(?:production|prod|live|netlify|vercel|aws|app store|play store)\b",
    r"\b(?:run|buy|purchase|launch|start)\s+(?:the\s+|a\s+|our\s+)?(?:paid|ad|advertising)\b",
    r"\bad spend\b|\badvertising budget\b|\bbuy ads\b|\bpaid campaign\b",
    r"\bsend\b.{0,40}\b(?:emails?|newsletters?|messages?)\b.{0,40}\b(?:customers?|users?|subscribers?|list)\b",
    r"\bemail the list\b",
    r"\b(?:charge|bill|refund|debit)\b.{0,30}\b(?:customers?|users?|cards?|clients?)\b",
    r"\b(?:make|process|initiate|execute|send)\b.{0,15}\b(?:payments?|payouts?|transfers?|wires?)\b",
    r"\btransfer funds\b",
    r"\b(?:sign|execute|countersign)\b.{0,25}\b(?:contracts?|agreements?|nda)\b",
    r"\b(?:delete|terminate|drop|wipe)\b.{0,30}\b(?:accounts?|data|database|users?|records?|subscriptions?|production)\b",
    r"\bcancel subscriptions?\b",
]
_ACTION_RE = re.compile("|".join(f"(?:{p})" for p in _ACTION_PATTERNS))


def keyword_flags_hitl(instruction: str, title: str = "") -> bool:
    """True when the task performs/commits to a real-world action."""
    text = (instruction or title or "").strip().lower()
    combined = f"{title} {instruction}".lower()
    if _EXPLICIT_EXECUTION_RE.search(combined):
        return True
    if _DRAFTING_LEAD_RE.match(text):
        return False
    return bool(_ACTION_RE.search(combined))


class HITLGate:
    def __init__(self):
        self._approved: set[str] = set()

    def apply(self, graph: TaskGraph) -> None:
        """Only ever turns confirmation ON; the decomposer's own flag is respected."""
        for task in graph.tasks:
            if task.department == Department.LEGAL:
                task.requires_human_confirmation = True  # platform policy
            elif keyword_flags_hitl(task.instruction, task.title):
                task.requires_human_confirmation = True

    def should_gate_now(self, task: StructuredTask) -> bool:
        return task.requires_human_confirmation and task.task_id not in self._approved

    def approve(self, task_id: str) -> None:
        self._approved.add(task_id)

    def is_approved(self, task_id: str) -> bool:
        return task_id in self._approved

    def pending_ids(self, graph: TaskGraph) -> List[str]:
        return [t.task_id for t in graph.pending_hitl()] if graph is not None else []

    def pending_confirmations(self, graph: TaskGraph) -> List[str]:
        """Titles of tasks currently awaiting the founder."""
        if graph is None:
            return []
        return [t.title for t in graph.pending_hitl()]
