import asyncio, os
import pytest
from neefeel import llm
from neefeel.builder.code_builder import CodeBuilderEngine, parse_project
from neefeel.builder.preview import write_project_and_preview
from neefeel.executives.engineering import EngineeringExecutive
from neefeel.models import Department as D, GeneratedFile, GeneratedProject
from helpers import mk

GOOD = """PROJECT: Portal App
=== FILE: index.html ===
<!DOCTYPE html><html><body>"quotes" and {braces}
<script src="app.js"></script></body></html>
=== END FILE ===
=== FILE: app.js ===
console.log("hi\\n");
=== END FILE ==="""


def test_parse_delimited_json_fallback_and_html_fallback():
    p = parse_project("<think>x</think>" + GOOD)
    assert p.project_name == "Portal App" and [f.path for f in p.files] == ["index.html", "app.js"]
    assert '"quotes" and {braces}' in p.files[0].content                   # no escaping needed
    legacy = parse_project('{"project_name":"x","files":[{"path":"index.html","content":"<html></html>"}]}')
    assert legacy.files[0].path == "index.html"
    assert parse_project("```html\n<html><body>hi</body></html>\n```").files[0].path == "index.html"
    for bad in ("sorry, I can't", "=== FILE: a.js ===\nx\n=== END FILE ==="):
        with pytest.raises(ValueError):
            parse_project(bad)


def test_path_traversal_is_neutralized(tmp_path):
    proj = GeneratedProject(project_name="Demo!", files=[
        GeneratedFile(path="index.html", content="<html/>"), GeneratedFile(path="../../evil.txt", content="x"),
        GeneratedFile(path="/abs/evil2.txt", content="x")])
    r = write_project_and_preview(proj, str(tmp_path / "root"))
    assert all(os.path.commonpath([f, r.project_dir]) == r.project_dir for f in r.files)
    assert not (tmp_path / "evil.txt").exists() and r.opened is False       # auto_open defaults to False


def _fake_ask(replies):
    it = iter(replies)
    async def fake(model_client, **kw): return next(it)
    return fake


def test_engineering_builds_real_prototype_and_honours_status_and_risks(tmp_path, monkeypatch):
    arch = "Architecture.\n\nRisks:\n- contradicts Product's scope: realtime sync\nSTATUS: blocked_on_hitl"
    monkeypatch.setattr(llm, "ask", _fake_ask([arch, GOOD]))
    ex = EngineeringExecutive(object(), str(tmp_path))
    task = mk("T3", D.ENGINEERING, title="Prototype the portal", instr="Build the web app prototype", should_build=True)
    res = asyncio.run(ex.handle(task, {"run_id": "r1"}))
    assert res.status == "blocked_on_hitl"                                    # used to be hard-coded "completed"
    assert res.risks == ["contradicts Product's scope: realtime sync"]        # used to be []
    idx = res.data["preview"]["index_path"]
    assert "quotes" in open(idx).read() and "/r1/" in idx.replace("\\", "/")  # the REAL build, not a placeholder
    assert any(a.endswith("T3_deliverable.md") for a in res.artifacts) and any(a.endswith("app.js") for a in res.artifacts)


def test_build_trigger_is_whole_word_and_respects_flag():
    w = EngineeringExecutive.wants_build
    assert not w(mk("T", D.ENGINEERING, title="Security requirements", instr="Define the approach to auth"))  # 'ui'/'app' substrings
    assert w(mk("T", D.ENGINEERING, instr="Build a clickable prototype"))
    assert not w(mk("T", D.ENGINEERING, instr="Build a clickable prototype", should_build=False))
    assert w(mk("T", D.ENGINEERING, instr="Write the schema", should_build=True))


def test_build_failure_is_reported_not_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "ask", _fake_ask(["Plan.\nRisks: None", "nope", "still nope"]))
    ex = EngineeringExecutive(object(), str(tmp_path))
    res = asyncio.run(ex.handle(mk("T3", D.ENGINEERING, should_build=True), {}))
    assert res.status == "completed" and "preview" not in res.data
    assert any(r.startswith("Prototype build failed") for r in res.risks) and "build_error" in res.data


def test_non_build_engineering_task_makes_no_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "ask", _fake_ask(["Schema doc.\nRisks: None"]))
    res = asyncio.run(EngineeringExecutive(object(), str(tmp_path)).handle(mk("T3", D.ENGINEERING, should_build=False), {}))
    assert res.data == {} and len(res.artifacts) == 1
