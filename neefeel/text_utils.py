"""
Shared text-parsing helpers.

The configured model (Fireworks/DeepSeek) does not support AutoGen's
structured-output path, so every place that wants typed data gets raw text
and recovers structure from it here. Everything that parses model text lives
in this one module so prompts and parsers can be kept aligned.
"""

from __future__ import annotations

import json
import re
from typing import List, Tuple

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Removes reasoning blocks. Also handles providers that drop the opening
    tag and only emit a closing </think>."""
    text = text or ""
    text = _THINK_BLOCK_RE.sub("", text)
    if "<think>" not in text.lower() and "</think>" in text.lower():
        text = re.split(r"</think>", text, maxsplit=1, flags=re.IGNORECASE)[1]
    return text.strip()


def extract_json(text: str) -> dict:
    """Pulls a JSON object out of a model response: strips reasoning blocks and
    code fences, then takes the outermost {...} span. Raises
    json.JSONDecodeError if nothing usable is found."""
    text = strip_think(text)
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at the top level")
    return data


# -- Free-text status/risk parsing for executives -----------------------------------------
#
# Every executive prompt is followed by OUTPUT_FORMAT_INSTRUCTIONS, which asks for
#
#     Risks:
#     - first risk
#     - second risk
#     STATUS: blocked_on_hitl        <- only when sign-off is needed
#
# The parser below is tolerant of common markdown drift (**Risks:**, ## Risks,
# numbered lists) but is strict about the STATUS signal: it must be an explicit
# "STATUS: blocked_on_hitl" line, so prose such as "this does NOT need approval"
# can never block a task.

_STATUS_LINE_RE = re.compile(
    r"^[\s>*_`#-]*status[\s*_`]*[:=][\s*_`]*blocked_on_hitl\b", re.IGNORECASE | re.MULTILINE
)
_RISK_HEADER_RE = re.compile(
    r"^[\s>#]*[*_]{0,2}\s*risks?\s*[*_]{0,2}\s*(?::\s*[*_]{0,2}\s*(?P<inline>.*))?$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(?P<text>.+?)\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_CONTRADICTS_RE = re.compile(r"contradicts[^.\n]*", re.IGNORECASE)
_NONE_VALUES = {"none", "none.", "n/a", "na", "none identified", "no risks", "nothing"}


def _clean(text: str) -> str:
    return re.sub(r"[*_`]{1,3}", "", text).strip().strip("-").strip()


def _parse_risks_section(raw_text: str) -> List[str]:
    lines = raw_text.splitlines()
    header_idx = None
    inline = ""
    for i, line in enumerate(lines):  # the LAST header is the footer the prompt asks for
        m = _RISK_HEADER_RE.match(line)
        if m:
            header_idx, inline = i, (m.group("inline") or "").strip()
    if header_idx is None:
        return []

    risks: List[str] = []
    if inline and _clean(inline).lower() not in _NONE_VALUES:
        risks.append(_clean(inline))

    seen_bullet = False
    for line in lines[header_idx + 1 :]:
        if not line.strip():
            if seen_bullet:
                break
            continue
        if _HEADING_RE.match(line) or _STATUS_LINE_RE.match(line):
            break
        bullet = _BULLET_RE.match(line)
        if bullet:
            seen_bullet = True
            item = _clean(bullet.group("text"))
            if item and item.lower() not in _NONE_VALUES:
                risks.append(item)
        elif not seen_bullet and not risks:
            item = _clean(line)  # "Risks:" followed by a plain sentence
            if item and item.lower() not in _NONE_VALUES:
                risks.append(item)
            break
        else:
            break
    return risks


def infer_status_and_risks(raw_text: str) -> Tuple[str, List[str]]:
    """Returns ('completed' | 'blocked_on_hitl', [risk strings])."""
    raw_text = strip_think(raw_text or "")
    status = "blocked_on_hitl" if _STATUS_LINE_RE.search(raw_text) else "completed"
    risks = _parse_risks_section(raw_text)

    # Cross-department conflict phrasing ("contradicts Product's pricing: ...") is
    # what safety/conflict.py keys on; capture it wherever it appears.
    for match in _CONTRADICTS_RE.finditer(raw_text):
        phrase = _clean(match.group(0))
        if phrase and not any(phrase in r for r in risks):
            risks.append(phrase)
    return status, risks


OUTPUT_FORMAT_INSTRUCTIONS = """

OUTPUT FORMAT (machine-read, follow exactly):
- Write the deliverable first, in plain markdown.
- Finish with a section whose first line is exactly `Risks:` followed by one risk per \
line, each starting with "- " (write `Risks: None` if there genuinely are none). \
Do not bold or number the Risks header.
- If this task involves a real financial commitment, a live deployment, a binding \
legal document, or any other action that must not proceed without the founder's \
explicit sign-off, add one final line reading exactly:
STATUS: blocked_on_hitl
- Do not write the STATUS line anywhere else, and do not mention it in prose.
"""
