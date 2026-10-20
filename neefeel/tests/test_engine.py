import asyncio
from collections import Counter
from neefeel.memory.embeddings import DeterministicHashEmbedding
from neefeel.memory.persistent_store import InMemoryPersistentStore
from neefeel.memory.scopes import CompanyMemory
from neefeel.models import Department as D, TaskStatus as S
from neefeel.orchestration.engine import TaskOrchestrationEngine
from neefeel.orchestration.task_graph import TaskGraph
from neefeel.safety.hitl import HITLGate
from helpers import mk, ok


def build(tasks, handler):
    g = TaskGraph(tasks); gate = HITLGate(); gate.apply(g)
    mem = CompanyMemory(InMemoryPersistentStore(DeterministicHashEmbedding()))
    return g, TaskOrchestrationEngine(g, {d: handler for d in D}, mem, gate, run_id="r1")


def statuses(g):
    return {t.task_id: t.status.value for t in g.tasks}


def test_dependency_chain_runs_and_passes_upstream_output():
    seen = {}
    async def h(task, ctx):
        seen[task.task_id] = dict(ctx["task"]); return ok(task, f"OUT-{task.task_id}")
    g, e = build([mk("T1"), mk("T2", D.DESIGN, ["T1"]), mk("T3", D.ENGINEERING, ["T1", "T2"])], h)
    asyncio.run(e.run())
    assert statuses(g) == {"T1": "completed", "T2": "completed", "T3": "completed"}   # used to raise AttributeError
    assert seen["T1"] == {}
    assert list(seen["T2"].values()) == ["OUT-T1"]                                     # used to be {}
    assert sorted(seen["T3"].values()) == ["OUT-T1", "OUT-T2"]


def test_independent_tasks_run_in_one_parallel_wave():
    active, peak = 0, 0
    async def h(task, ctx):
        nonlocal active, peak
        active += 1; peak = max(peak, active); await asyncio.sleep(0.05); active -= 1
        return ok(task)
    g, e = build([mk("T1"), mk("T2", D.GROWTH), mk("T3", D.DESIGN)], h)
    asyncio.run(e.run())
    assert peak == 3


def test_pre_run_gate_then_approve_resumes_blocked_branch():
    async def h(task, ctx): return ok(task)
    tasks = [mk("T1"), mk("T2", D.LEGAL, ["T1"]), mk("T3", D.FINANCE, ["T2"]), mk("T4", D.GROWTH, ["T1"]), mk("T5", D.DESIGN, ["T4"])]
    g, e = build(tasks, h)
    asyncio.run(e.run())
    assert statuses(g) == {"T1": "completed", "T2": "blocked_on_hitl", "T3": "blocked_on_dependency", "T4": "completed", "T5": "completed"}
    asyncio.run(e.approve_multiple(["T2"]))
    assert all(s == "completed" for s in statuses(g).values())                          # T3 used to stay blocked forever


def test_post_run_review_is_accepted_without_rerun():
    calls = Counter()
    async def h(task, ctx):
        calls[task.task_id] += 1
        return ok(task, "DRAFT text", status="blocked_on_hitl")
    g, e = build([mk("T1", D.FINANCE), mk("T2", D.PEOPLE, ["T1"])], h)
    asyncio.run(e.run())
    assert statuses(g)["T1"] == "blocked_on_hitl" and statuses(g)["T2"] == "blocked_on_dependency"
    assert e.held_result("T1").output == "DRAFT text"
    asyncio.run(e.approve_multiple(["T1"]))
    assert calls["T1"] == 1                                       # approval does NOT call the executive again
    assert statuses(g)["T1"] == "completed"
    assert e.results["T1"].output == "DRAFT text"
    assert calls["T2"] == 1 and statuses(g)["T2"] == "blocked_on_hitl"   # T2 itself asks for review in this stub


def test_preapproved_task_is_not_asked_twice():
    async def h(task, ctx): return ok(task, "binding text", status="blocked_on_hitl")
    g, e = build([mk("T1", D.LEGAL)], h)                          # legal -> pre-run gate
    asyncio.run(e.run()); assert statuses(g)["T1"] == "blocked_on_hitl"
    asyncio.run(e.approve_multiple(["T1"]))                       # authorizes the run
    assert statuses(g)["T1"] == "completed"                       # used to loop forever in blocked_on_hitl


def test_executive_exception_fails_only_that_task():
    async def h(task, ctx):
        if task.task_id == "T2": raise RuntimeError("network down")
        return ok(task)
    g, e = build([mk("T1"), mk("T2", D.GROWTH), mk("T3", D.DESIGN, ["T2"])], h)
    results = asyncio.run(e.run())                                # used to raise out of run()
    assert statuses(g) == {"T1": "completed", "T2": "failed", "T3": "blocked_on_dependency"}
    assert "network down" in e.results["T2"].output and len(results) == 2


def test_reject_and_modify():
    runs = []
    async def h(task, ctx):
        if task.task_id == "T1": runs.append(task.instruction)
        return ok(task, status="blocked_on_hitl")
    g, e = build([mk("T1", D.FINANCE), mk("T2", D.PEOPLE, ["T1"])], h)
    asyncio.run(e.run())
    asyncio.run(e.modify_and_resume("T1", "New instruction"))
    assert runs == ["Write a spec for the product.", "New instruction"] and statuses(g)["T1"] == "completed"
    g, e = build([mk("T1", D.FINANCE), mk("T2", D.PEOPLE, ["T1"])], h)
    asyncio.run(e.run()); asyncio.run(e.reject("T1", "no"))
    assert statuses(g) == {"T1": "failed", "T2": "blocked_on_dependency"} and "no" in e.results["T1"].output


def test_results_have_one_entry_per_task_after_approval():
    async def h(task, ctx): return ok(task)
    g, e = build([mk("T1", D.LEGAL)], h)
    asyncio.run(e.run()); res = asyncio.run(e.approve_multiple(["T1"]))
    assert [r.task_id for r in res] == ["T1"] and res[0].status == "completed"
