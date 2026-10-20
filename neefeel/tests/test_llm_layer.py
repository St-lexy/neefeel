import asyncio
import pytest
from autogen_ext.models.replay import ReplayChatCompletionClient
from neefeel import llm


def test_every_call_is_stateless():
    c = ReplayChatCompletionClient(["one", "two"])
    for prompt in ("task ONE", "task TWO"):
        asyncio.run(llm.ask(c, name="x", system_message="SYS", prompt=prompt))
    assert len(c.create_calls[1]["messages"]) == 2          # system + this prompt only; used to be 4 (history leaked)
    assert "task ONE" not in str(c.create_calls[1]["messages"])


def test_json_repair_round_trip_and_failure():
    c = ReplayChatCompletionClient(["not json", '{"a": 1}'])
    assert asyncio.run(llm.ask_json(c, name="x", system_message="S", prompt="P")) == {"a": 1}
    assert "rejected" in str(c.create_calls[1]["messages"][-1].content)
    c = ReplayChatCompletionClient(["bad", "worse"])
    with pytest.raises(llm.LLMJSONError) as e:
        asyncio.run(llm.ask_json(c, name="x", system_message="S", prompt="P"))
    assert e.value.raw == "worse"


def test_transient_error_is_retried(monkeypatch):
    calls = {"n": 0}
    class Flaky:
        pass
    from autogen_agentchat.agents import AssistantAgent
    orig = AssistantAgent.on_messages
    async def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1: raise ConnectionError("blip")
        return await orig(self, *a, **k)
    monkeypatch.setattr(AssistantAgent, "on_messages", flaky)
    real_sleep = asyncio.sleep
    async def fast_sleep(_delay): await real_sleep(0)
    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    assert asyncio.run(llm.ask(ReplayChatCompletionClient(["ok"]), name="x", system_message="S", prompt="P")) == "ok"
    assert calls["n"] == 2
