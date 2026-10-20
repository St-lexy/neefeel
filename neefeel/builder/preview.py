"""
Phase 3: Local file-system integration + optional web preview.

Writes a `GeneratedProject` to disk using sanitized, cross-platform paths and
(optionally) opens the resulting index.html in the default browser. Auto-open
is OFF by default: on a server/dashboard a browser pop-up is a side effect
nobody asked for. The CLI demo turns it on.
"""

from __future__ import annotations

import re
import webbrowser
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from ..models import GeneratedProject


class PreviewResult(BaseModel):
    project_dir: str
    index_path: str
    opened: bool
    note: str = ""
    files: List[str] = Field(default_factory=list)  # absolute paths actually written


def _sanitize_path_segment(segment: str) -> str:
    """Strip anything that could escape the project directory or break on
    a given OS: no '..', no absolute paths, no illegal filename chars."""
    segment = segment.replace("\\", "/")
    parts = [p for p in segment.split("/") if p not in ("", ".", "..")]
    cleaned = [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p) for p in parts]
    if not cleaned:
        raise ValueError(f"Path '{segment}' sanitizes to nothing")
    return "/".join(cleaned)


def _sanitize_project_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-")
    return slug or "neefeel-project"


def write_project_and_preview(
    project: GeneratedProject, root_dir: str = "./neefeel_projects", auto_open: bool = False
) -> PreviewResult:
    if not project.files:
        raise ValueError("Generated project has no files")

    project_slug = _sanitize_project_name(project.project_name)
    project_dir = (Path(root_dir).expanduser().resolve() / project_slug)
    project_dir.mkdir(parents=True, exist_ok=True)

    written_paths: List[Path] = []
    for f in project.files:
        safe_relative = _sanitize_path_segment(f.path)
        file_path = (project_dir / safe_relative).resolve()
        file_path.relative_to(project_dir)  # defense in depth: raises if it escaped
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f.content, encoding="utf-8")
        written_paths.append(file_path)

    index_candidates = [p for p in written_paths if p.name.lower() == "index.html"]
    index_path = index_candidates[0] if index_candidates else (
        next((p for p in written_paths if p.suffix.lower() in (".html", ".htm")), written_paths[0])
    )

    opened = False
    note = ""
    if auto_open:
        try:
            opened = webbrowser.open(index_path.as_uri())
        except Exception as exc:  # headless/sandboxed environments have no browser
            note = f"Could not auto-open a browser: {exc}. Open the file manually."
        if not opened and not note:
            note = "No browser available to auto-open in this environment."

    return PreviewResult(
        project_dir=str(project_dir),
        index_path=str(index_path),
        opened=opened,
        note=note,
        files=[str(p) for p in written_paths],
    )
