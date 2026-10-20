"""
Phase 3: The Builder Engine.

Turns a spec into a complete set of browser-runnable files.

Output format: the model emits delimited file blocks, NOT a JSON document.
Putting whole HTML/CSS/JS files inside JSON strings requires the model to
escape every quote and newline correctly across thousands of characters, which
reasoning models routinely get wrong. Delimited blocks need no escaping.
`parse_project` still accepts the old JSON shape as a fallback.
"""

from __future__ import annotations

import re
from typing import Any

from .. import llm
from ..models import GeneratedFile, GeneratedProject
from ..text_utils import extract_json, strip_think

BUILDER_SYSTEM_PROMPT = """You are an expert Frontend Prototype Engineer for Neefeel.
You build complete, interactive, single-page web applications for founders.

STRICT EXECUTION RULES:
1. PURE BROWSER-RUNNABLE CODE ONLY:
   - Output standard HTML5, CSS3, and modern Vanilla JavaScript (ES6+).
   - NEVER generate framework templates or build artifacts (NO SvelteKit, Next.js, Nuxt, JSX, or uncompiled TypeScript).
   - The prototype MUST run when index.html is opened directly in a browser (file://).

2. COMPLETE & SELF-CONTAINED:
   - Prefer a single `index.html` with all styles in `<style>` and all logic in `<script>`; separate local style.css / app.js files are also fine if index.html links them with relative paths.
   - You MAY use public CDN links (e.g. Tailwind CSS CDN, Lucide / FontAwesome icons).
   - ZERO placeholders: write every form handler, state update, modal toggle, mock payment flow and UI interaction in full. No "...", no "TODO".

3. STATE & PERSISTENCE:
   - Use browser `localStorage` for persisting data (invoices, tasks, settings, profiles).
   - Payments are SIMULATED: show a clean modal/popup payment simulation that updates the UI state on completion. Never call a real payment API or embed real keys.

OUTPUT FORMAT — CRITICAL (machine-parsed, no JSON):
First line:  PROJECT: short-project-name
Then, for every file:
=== FILE: index.html ===
<the complete file content, raw, exactly as it should be saved>
=== END FILE ===
Repeat the FILE block for each additional file (e.g. style.css, app.js).
Do NOT wrap file content in markdown code fences. Do NOT output <think> tags or any
text outside the PROJECT line and the FILE blocks. There must be an index.html.
"""

_PROJECT_RE = re.compile(r"^\s*PROJECT:\s*(?P<name>.+?)\s*$", re.MULTILINE)
_FILE_RE = re.compile(
    r"^=== FILE:\s*(?P<path>.+?)\s*===[ \t]*\n(?P<body>.*?)\n?^=== END FILE ===",
    re.DOTALL | re.MULTILINE,
)
_OPEN_FILE_RE = re.compile(r"^=== FILE:\s*(?P<path>.+?)\s*===[ \t]*\n", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\n(?P<body>.*?)\n```\s*$", re.DOTALL)
_HTML_FENCE_RE = re.compile(r"```html\s*\n(?P<body>.*?)```", re.DOTALL | re.IGNORECASE)


def _unfence(body: str) -> str:
    m = _FENCE_RE.match(body)
    return m.group("body") if m else body


def parse_project(raw_text: str) -> GeneratedProject:
    """Raises ValueError if no usable project can be recovered."""
    text = strip_think(raw_text)

    files = [
        GeneratedFile(path=m.group("path").strip(), content=_unfence(m.group("body")))
        for m in _FILE_RE.finditer(text)
    ]
    name_match = _PROJECT_RE.search(text)
    name = name_match.group("name") if name_match else "neefeel-project"

    if files:
        # A reply cut off by the token limit leaves a last FILE block with no END marker.
        last_end = max(m.end() for m in _FILE_RE.finditer(text))
        tail = text[last_end:]
        m = _OPEN_FILE_RE.search(tail)
        if m:
            body = tail[m.end():]
            path = m.group("path").strip()
            if path.lower().endswith((".html", ".htm")) and "</html>" not in body.lower():
                raise ValueError(f"reply was truncated inside {path} (output token limit reached)")
            if body.strip():
                files.append(GeneratedFile(path=path, content=_unfence(body.rstrip())))
    else:
        opened = _OPEN_FILE_RE.search(text)
        if opened:  # FILE block(s) started but never ended
            body = text[opened.end():]
            path = opened.group("path").strip()
            if "</html>" in body.lower() or not path.lower().endswith((".html", ".htm")):
                files = [GeneratedFile(path=path, content=_unfence(body.rstrip()))] if path.lower().endswith((".html", ".htm")) else []
            if not files:
                raise ValueError(f"reply was truncated inside {path} (output token limit reached)")

    if not files:  # legacy JSON shape
        try:
            data = extract_json(text)
            files = [GeneratedFile(path=f["path"], content=f["content"]) for f in data["files"]]
            name = data.get("project_name", name)
        except Exception:
            pass

    if not files:  # a lone ```html block is still a runnable prototype
        m = _HTML_FENCE_RE.search(text)
        if m:
            files = [GeneratedFile(path="index.html", content=m.group("body").strip())]

    files = [f for f in files if f.path.strip() and f.content.strip()]
    if not files:
        raise ValueError("no FILE blocks (or JSON files) found in the model response")
    if not any(f.path.lower().endswith((".html", ".htm")) for f in files):
        raise ValueError("project has no HTML file to open as a preview")
    return GeneratedProject(project_name=name, files=files)


class CodeBuilderEngine:
    def __init__(self, model_client: Any):
        self._model_client = model_client

    async def generate(self, spec: str) -> GeneratedProject:
        """Fails loudly (ValueError carrying the raw reply head) rather than
        returning an empty project. One repair round-trip on a parse failure."""
        prompt, raw, last_err = spec, "", None
        for _ in range(2):
            raw = await llm.ask(
                self._model_client, name="code_builder",
                system_message=BUILDER_SYSTEM_PROMPT, prompt=prompt,
                source="engineering_executive",
            )
            try:
                return parse_project(raw)
            except ValueError as exc:
                last_err = exc
                prompt = (
                    f"{spec}\n\n---\nYour previous reply could not be used: {exc}.\n"
                    "Reply again using EXACTLY the PROJECT line and === FILE: path === / "
                    "=== END FILE === blocks, including a complete index.html. "
                    "Keep it COMPACT so it fits: a single index.html (inline CSS and JS), "
                    "under about 400 lines, focused on the core screens and interactions."
                )
        raise ValueError(
            f"CodeBuilderEngine: could not parse a project from the model's response "
            f"({last_err}). Raw response started with: {raw[:300]!r}"
        )
