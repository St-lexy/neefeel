"""
Session Conversation State & Context Manager.
Maintains persistent multi-turn history across all executive calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from autogen_agentchat.messages import TextMessage


@dataclass
class ConversationTurn:
    role: str
    content: str
    department: Optional[str] = None
    task_id: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)


class SessionConversationManager:
    """Retains persistent context across prompts and executive dispatches."""

    def __init__(self, max_history_turns: int = 12):
        self.max_history_turns = max_history_turns
        self.history: List[ConversationTurn] = []
        self.artifacts_index: Dict[str, str] = {}

    def add_turn(
        self,
        role: str,
        content: str,
        department: Optional[str] = None,
        task_id: Optional[str] = None,
        artifacts: Optional[List[str]] = None,
    ) -> None:
        turn = ConversationTurn(
            role=role,
            content=content,
            department=department,
            task_id=task_id,
            artifacts=artifacts or [],
        )
        self.history.append(turn)
        if artifacts:
            for art in artifacts:
                self.artifacts_index[art] = task_id or role

    def clear(self) -> None:
        self.history.clear()
        self.artifacts_index.clear()

    def get_conversation_context(self) -> str:
        """Returns the sliding window of recent conversation history."""
        recent = self.history[-self.max_history_turns :]
        if not recent:
            return "No previous conversation history."

        lines = ["### Session Conversation Context:"]
        for t in recent:
            source = f"[{t.department.upper()}]" if t.department else f"[{t.role.upper()}]"
            art_note = f" (Artifacts: {', '.join(t.artifacts)})" if t.artifacts else ""
            lines.append(f"{source}: {t.content}{art_note}")
        return "\n".join(lines)

    def to_autogen_messages(self) -> List[TextMessage]:
        """Formats conversation history for AutoGen agent prompts."""
        recent = self.history[-self.max_history_turns :]
        messages = []
        for t in recent:
            src = t.department or t.role
            messages.append(TextMessage(content=t.content, source=src))
        return messages