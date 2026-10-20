import asyncio, json
import pytest
from neefeel import cofounder as cf, llm
from neefeel.models import Department as D

PLAN = {"founder_prompt": "x", "summary": "plan", "tasks": [
    {"task_id": "T1", "department": "product", "title": "PRD", "instruction": "Write the PRD incl. pricing tiers", "depends_on": []},
    {"task_id": "T2", "department": "finance", "title": "Unit economics", "instruction": "Model unit economics", "depends_on": ["T1"]},
    {"task_id": "T3", "department": "legal", "title": "ToS", "instruction": "Draft the ToS", "depends_on": ["T1"]},
    {"task_id": "T4", "department": "growth", "title": "GTM", "instruction": "Write positioning and the channel plan", "depends_on": []},
    {"task_id": "T5", "department": "design", "title": "UX", "instruction": "Design the flows", "depends_on": ["T1"]}]}


class FakeLLM:
    def __init__(self, plan=PLAN):
        self.plan, self.calls = plan, []

    async def __call__(self, model_client, *, name, system_message, prompt, **kw):
        self.calls.append((name, prompt))
        if name == "intent_decomposer": return json.dumps(self.plan)
        if name == "executive_synthesizer": return json.dumps({"strategy_summary": "S", "risks": [], "conflicts": [], "next_actions": []})
        if name == "conflict_resolver": return json.dumps({"description": "pricing mismatch", "recommended_resolution": "align", "alternatives": ["a"]})
        if name == "cofounder_dialogue": return "plain prose, not json"
        tail = {"financeexecutive": "Risks:\n- contradicts Product's pricing: tiers lose money",
                "legalexecutive": "Risks:\n- Binding arbitration clause\nSTATUS: blocked_on_hitl"}.get(name, "Risks: None")
        return f"# {name} deliverable\nBody text that is long. " + "x" * 800 + f"\n\n{tail}"

    def prompts_for(self, name): return [p for n, p in self.calls if n == name]


@pytest.fixture
def co(tmp_path, monkeypatch):
    fake = FakeLLM(); monkeypatch.setattr(llm, "ask", fake)
    c = cf.AICofounder(model="m", base_url="http://localhost:1", api_key="k", project_root=str(tmp_path))
    c.fake = fake
    yield c
    asyncio.run(c.close())


def test_full_run_with_approval_conflict_and_briefing(co):
    plan = asyncio.run(co.decompose("Build X"))
    results = asyncio.run(co.execute(plan))
    st = {r.task_id: r.status for r in results}
    assert st["T1"] == st["T4"] == "completed" and st["T3"] == "blocked_on_hitl"          # legal pre-run gate

    # Design/Finance really received Product's output (used to be empty)
    for name in ("financeexecutive", "designexecutive"):
        assert "Upstream Dependency Output" in co.fake.prompts_for(name)[0]
        assert "productexecutive deliverable" in co.fake.prompts_for(name)[0]
    assert "Upstream Dependency Output" not in co.fake.prompts_for("productexecutive")[0]

    legal_calls = len(co.fake.prompts_for("legalexecutive"))
    after = asyncio.run(co.approve("T3"))
    assert len(co.fake.prompts_for("legalexecutive")) == legal_calls + 1                  # ran once after authorization
    assert {r.task_id: r.status for r in after}["T3"] == "completed"                      # used to loop in blocked_on_hitl
    assert len(after) == 5 and len({r.task_id for r in after}) == 5                       # no duplicates

    b = asyncio.run(co.synthesize("Build X", plan))                                       # results defaulted from engine
    assert len(b.deliverables) == 5 and not any("requires founder authorization" in d for d in b.deliverables)
    assert b.deliverables[0].startswith("T1 (product) — PRD: productexecutive deliverable")
    assert any("pricing mismatch" in c for c in b.conflicts)                              # conflict detected + resolved
    assert any("Binding arbitration" in r or "tiers lose money" in r for r in b.risks)    # risks survive into briefing
    payload = json.loads(co.fake.prompts_for("executive_synthesizer")[0])
    assert {"risks", "output_head", "status", "title"} <= set(payload["results"][0]) and "task_status" in payload
    assert len(payload["results"]) == 5                                                    # deduped


def test_synthesis_lists_pending_confirmations_and_survives_model_failure(co, monkeypatch):
    plan = asyncio.run(co.decompose("Build X")); asyncio.run(co.execute(plan))
    async def broken(model_client, **kw):
        raise RuntimeError("provider down")
    monkeypatch.setattr(llm, "ask", broken)
    b = asyncio.run(co.synthesize("Build X", plan))
    assert b.pending_confirmations == ["ToS"] and any("ToS" in a for a in b.next_actions)
    assert "Automatic briefing unavailable" in b.strategy_summary
    assert len(b.deliverables) >= 3


def test_executive_outputs_are_isolated_per_run_directory(co, tmp_path):
    plan = asyncio.run(co.decompose("Build X"))
    asyncio.run(co.execute(plan)); first = co._active_run_id
    asyncio.run(co.execute(plan)); second = co._active_run_id
    assert first != second
    assert (tmp_path / first / "deliverables" / "T1_deliverable.md").exists()
    assert (tmp_path / second / "deliverables" / "T1_deliverable.md").exists()


def test_session_records_each_completed_result_once(co):
    plan = asyncio.run(co.decompose("Build X")); asyncio.run(co.execute(plan)); asyncio.run(co.approve("T3"))
    execs = [t for t in co.session_manager.history if t.role == "executive"]
    assert sorted(t.task_id for t in execs) == ["T1", "T2", "T3", "T4", "T5"]


def test_chat_falls_back_to_plain_text_instead_of_crashing(co):
    d = asyncio.run(co.chat("hello"))
    assert d.intent == "conversational_inquiry" and d.reply == "plain prose, not json"


def test_decompose_repairs_a_cyclic_plan_once(tmp_path, monkeypatch):
    bad = json.loads(json.dumps(PLAN)); bad["tasks"][0]["depends_on"] = ["T2"]            # T1<->T2 cycle
    replies = iter([json.dumps(bad), json.dumps(PLAN)]); seen = []
    async def fake(model_client, *, name, system_message, prompt, **kw):
        seen.append(prompt); return next(replies)
    monkeypatch.setattr(llm, "ask", fake)
    c = cf.AICofounder(model="m", base_url="http://localhost:1", api_key="k", project_root=str(tmp_path))
    plan = asyncio.run(c.decompose("Build X"))
    assert len(plan.tasks) == 5 and "Cycle detected" in seen[1] and plan.founder_prompt == "Build X"


def test_reset_session_clears_run_state(co):
    asyncio.run(co.execute(asyncio.run(co.decompose("Build X"))))
    co.reset_session()
    assert co.current_results() == [] and co._active_graph is None and co.session_manager.history == []


@pytest.mark.parametrize("env,args,expected", [
    ({"FIREWORKS_API_KEY": "fw", "CEREBRAS_API_KEY": "ce"}, {}, ("fw", "https://api.fireworks.ai/inference/v1")),
    ({"CEREBRAS_API_KEY": "ce"}, {}, ("ce", "https://api.cerebras.ai/v1")),     # used to go to Fireworks' host
    ({"OPENAI_API_KEY": "oa"}, {}, ("oa", "https://api.openai.com/v1")),        # used to go to Fireworks' host
    ({"CEREBRAS_API_KEY": "ce"}, {"base_url": "http://x/v1"}, ("ce", "http://x/v1")),
    ({}, {"api_key": "explicit"}, ("explicit", "https://api.fireworks.ai/inference/v1")),
])
def test_key_is_paired_with_its_own_base_url(monkeypatch, env, args, expected):
    for k in ("FIREWORKS_API_KEY", "FIREWORKS_BASE_URL", "CEREBRAS_API_KEY", "CEREBRAS_BASE_URL", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items(): monkeypatch.setenv(k, v)
    assert cf._resolve_endpoint(args.get("api_key"), args.get("base_url")) == expected
