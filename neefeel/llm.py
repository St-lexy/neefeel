"""
The one place that talks to the model.

Why this exists:
  * AutoGen's AssistantAgent is STATEFUL — it appends every prompt and reply to
    its own context. Long-lived agents therefore leak earlier tasks into later
    ones (breaking department isolation) and grow token cost on every call. Every
    call here builds a fresh agent, so each call sees exactly the prompt it is given.
  * Reasoning-model <think> blocks are stripped once, here.
  * Calls have a timeout and one retry for transient errors.
  * JSON replies that fail to parse/validate get one repair round-trip that
    shows the model what was wrong.

Callers use `llm.ask(...)` / `llm.ask_json(...)` through the module (not
`from llm import ask`) so tests can monkeypatch a single seam.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

from .text_utils import extract_json, strip_think

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 300.0
DEFAULT_ATTEMPTS = 2


class LLMJSONError(ValueError):
    """The model never produced a valid/accepted JSON reply. `.raw` is its last reply."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


async def ask(
    model_client: Any,
    *,
    name: str,
    system_message: str,
    prompt: str,
    source: str = "orchestrator",
    timeout: float = DEFAULT_TIMEOUT_S,
    attempts: int = DEFAULT_ATTEMPTS,
) -> str:
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        agent = AssistantAgent(name=name, model_client=model_client, system_message=system_message)
        try:
            response = await asyncio.wait_for(
                agent.on_messages([TextMessage(content=prompt, source=source)], CancellationToken()),
                timeout,
            )
            content = response.chat_message.content
            return strip_think(content if isinstance(content, str) else str(content))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # network, timeout, provider 5xx/429 ...
            last_exc = exc
            log.warning("LLM call %r failed (attempt %d/%d): %s", name, attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"LLM call '{name}' failed after {attempts} attempt(s): {last_exc}") from last_exc


async def ask_json(
    model_client: Any,
    *,
    name: str,
    system_message: str,
    prompt: str,
    validate: Optional[Callable[[dict], Any]] = None,
    repair_attempts: int = 1,
    source: str = "orchestrator",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Any:
    """Asks for a JSON object; returns `validate(data)` (or the dict itself)."""
    current_prompt = prompt
    raw, last_err = "", None
    for _ in range(repair_attempts + 1):
        raw = await ask(
            model_client, name=name, system_message=system_message,
            prompt=current_prompt, source=source, timeout=timeout,
        )
        try:
            data = extract_json(raw)
            return validate(data) if validate else data
        except Exception as exc:
            last_err = exc
            current_prompt = (
                f"{prompt}\n\n---\nYour previous reply was rejected: {exc}\n"
                f"Previous reply (truncated):\n{raw[:1500]}\n\n"
                "Return ONLY the corrected JSON object, with no commentary and no code fences."
            )
    raise LLMJSONError(f"'{name}' did not return acceptable JSON: {last_err}", raw=raw)
