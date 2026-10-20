"""Regression tests for 'executives cannot present a web preview'."""
import asyncio, json
import pytest
from neefeel import cofounder as cf, llm
from neefeel.builder.code_builder import parse_project
from neefeel.models import DecompositionPlan, Department as D
from helpers import mk

HTML = "<!DOCTYPE html><html><body>BUILT</body></html>"


def plan_of(*tasks): return DecompositionPlan(founder_prompt="x", summary="s", tasks=list(tasks))


def test_planner_that_omits_should_build_still_gets_a_build_task():
    # realistic titles that the strict whole-word check alone would have missed
    p = plan_of(mk("T1"), mk("T2", D.ENGINEERING, title="Technical Architecture and MVP Build",
                             instr="Design the architecture and implement the portal."),
                mk("T3", D.ENGINEERING, title="Data schema", instr="Define tables."))
    assert cf.ensure_build_task(p) == "T2"
    assert [t.should_build for t in p.tasks] == [None, True, False]


def test_deploy_task_is_never_chosen_over_the_build_task():
    p = plan_of(mk("T1", D.ENGINEERING, title="Netlify deploy", instr="Deploy to production on Netlify."),
                mk("T2", D.ENGINEERING, title="Portal", instr="Create the client portal app."))
    assert cf.ensure_build_task(p) == "T2"


def test_planner_choices_are_respected():
    p = plan_of(mk("T1", D.ENGINEERING, should_build=False), mk("T2", D.ENGINEERING, should_build=True))
    assert cf.ensure_build_task(p) == "T2"
    p = plan_of(mk("T1", D.ENGINEERING, should_build=False))
    assert cf.ensure_build_task(p) is None                      # explicit opt-out
    assert cf.ensure_build_task(plan_of(mk("T1"))) is None      # no engineering task


def test_truncated_replies():
    ok = parse_project("PROJECT: p\n=== FILE: index.html ===\n" + HTML)             # cut right after </html>, no END marker
    assert ok.files[0].content.strip() == HTML
    with pytest.raises(ValueError, match="truncated"):
        parse_project("PROJECT: p\n=== FILE: index.html ===\n<html><body><script>function x(){")
    two = parse_project(f"PROJECT: p\n=== FILE: index.html ===\n{HTML}\n=== END FILE ===\n=== FILE: app.js ===\nlet a = 1;\nlet b")
    assert [f.path for f in two.files] == ["index.html", "app.js"]                   # keeps a usable tail
    with pytest.raises(ValueError, match="truncated"):
        parse_project(f"PROJECT: p\n=== FILE: index.html ===\n<html><body>cut <script>")  # html itself cut


def test_output_budgets_are_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("NEELFEEL_MAX_TOKENS", raising=False); monkeypatch.delenv("NEELFEEL_BUILDER_MAX_TOKENS", raising=False)
    c = cf.AICofounder(model="m", base_url="http://x/v1", api_key="k", project_root=str(tmp_path))
    assert c._model_client._create_args["max_tokens"] == 8000
    assert c._builder_client._create_args["max_tokens"] == 24000
    assert c._executives[D.ENGINEERING].builder._model_client is c._builder_client
    asyncio.run(c.close())


def test_truncated_build_is_repaired_then_previewed_and_retry_works(tmp_path, monkeypatch):
    plan = {"founder_prompt": "x", "summary": "s", "tasks": [
        {"task_id": "T1", "department": "product", "title": "PRD", "instruction": "Write the PRD", "depends_on": []},
        {"task_id": "T2", "department": "engineering", "title": "Portal MVP Build",   # no should_build from the model
         "instruction": "Implement the client portal.", "depends_on": ["T1"]}]}
    builds = iter([
        "PROJECT: p\n=== FILE: index.html ===\n<html><body><script>fn(",            # 1: truncated
        f"PROJECT: p\n=== FILE: index.html ===\n{HTML}\n=== END FILE ===",           # repair succeeds
        "garbage", "garbage again",                                                   # later manual retry: fails twice
        f"PROJECT: p\n=== FILE: index.html ===\n{HTML}\n=== END FILE ===",           # then succeeds
    ])
    seen = []
    async def fake(mc, *, name, system_message, prompt, **kw):
        seen.append((name, prompt))
        if name == "intent_decomposer": return json.dumps(plan)
        if name == "code_builder": return next(builds)
        return "Doc.\n\nRisks: None"
    monkeypatch.setattr(llm, "ask", fake)
    co = cf.AICofounder(model="m", base_url="http://x/v1", api_key="k", project_root=str(tmp_path))
    p = asyncio.run(co.decompose("Build X"))
    assert [t.should_build for t in p.tasks if t.department == D.ENGINEERING] == [True]
    res = {r.task_id: r for r in asyncio.run(co.execute(p))}
    prev = res["T2"].data["preview"]
    assert "BUILT" in open(prev["index_path"]).read() and "COMPACT" in [pr for n, pr in seen if n == "code_builder"][1]
    assert not any("failed" in r for r in res["T2"].risks)

    # manual retry path (what the dashboard button calls)
    res["T2"].data.pop("preview")
    builds = iter(["garbage", "garbage again"] )
    r = asyncio.run(co.rebuild_prototype("T2"))
    assert "preview" not in r.data and r.data["build_error"] and any(x.startswith("Prototype build failed") for x in r.risks)
    builds = iter([f"PROJECT: p\n=== FILE: index.html ===\n{HTML}\n=== END FILE ==="])
    r = asyncio.run(co.rebuild_prototype("T2"))
    assert "preview" in r.data and "build_error" not in r.data and not any("build failed" in x for x in r.risks)
    asyncio.run(co.close())
