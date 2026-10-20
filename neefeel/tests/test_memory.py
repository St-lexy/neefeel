import asyncio
from neefeel.memory.embeddings import DeterministicHashEmbedding
from neefeel.memory.persistent_store import InMemoryPersistentStore
from neefeel.memory.scopes import CompanyMemory
from helpers import mk


def test_upstream_output_reaches_downstream_context():
    async def go():
        mem = CompanyMemory(InMemoryPersistentStore(DeterministicHashEmbedding()))
        mem.pass_upstream_output("T1", "T2", "PRD text", label="T1 · product · PRD")
        ctx = await mem.build_context_for_task(mk("T2"))
        assert ctx["task"] == {"T1 · product · PRD": "PRD text"}
        assert (await mem.build_context_for_task(mk("T3")))["task"] == {}
        mem.reset_task_context()
        assert (await mem.build_context_for_task(mk("T2")))["task"] == {}
    asyncio.run(go())


def test_department_facts_do_not_collide_across_runs():
    async def go():
        mem = CompanyMemory(InMemoryPersistentStore(DeterministicHashEmbedding()))
        t = mk("T1")
        await mem.record_result_as_department_fact(t, "run one output", "r1")
        await mem.record_result_as_department_fact(t, "run two output", "r2")
        texts = {r.text for r in await mem.get_department_context(t.department, "output")}
        assert texts == {"run one output", "run two output"}
    asyncio.run(go())
