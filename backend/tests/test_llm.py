"""Hedged Gemma calls and API key rotation: nothing may block a turn."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.agent import prompts
from app.agent.llm import LLM, _Key

OK = '{"reply": "Ciao a tutti"}'
HANG = object()
FAIL = object()
QUOTA = object()


def fake_key(label, responses, calls):
    async def generate_content(**_):
        calls.append(label)
        nxt = next(responses, HANG)
        if nxt is HANG:
            await asyncio.sleep(60)
        if nxt is FAIL:
            raise errors.ServerError(500, {"error": {"message": "Internal error"}})
        if nxt is QUOTA:
            raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
        return SimpleNamespace(text=nxt, usage_metadata=None)

    key = _Key.__new__(_Key)
    key.label, key.resting_until = label, 0.0
    key.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    return key


def make_llm(*per_key_responses, deadline_s=1.0):
    llm = LLM.__new__(LLM)
    llm.model, llm.thinking_level, llm.temperature = "m", "minimal", 0.7
    llm.deadline_s, llm.hedge_after_s, llm.max_parallel, llm.max_launches = deadline_s, 0.05, 2, 4
    llm.calls = []
    llm.keys = [
        fake_key(f"key{i + 1}", iter(responses), llm.calls)
        for i, responses in enumerate(per_key_responses)
    ]
    llm._active = 0
    return llm


async def test_slow_request_is_hedged():
    llm = make_llm([HANG, OK])
    out = await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert out.reply == "Ciao a tutti" and len(llm.calls) == 2


async def test_failed_request_is_replaced():
    llm = make_llm([FAIL, FAIL, OK])
    out = await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert out.reply == "Ciao a tutti"


async def test_gives_up_at_deadline():
    llm = make_llm([HANG, HANG, HANG, HANG], deadline_s=0.3)
    started = asyncio.get_running_loop().time()
    with pytest.raises(RuntimeError):
        await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert asyncio.get_running_loop().time() - started < 1


async def test_quota_error_switches_to_fallback_key():
    llm = make_llm([QUOTA], [OK, OK])
    out = await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert out.reply == "Ciao a tutti"
    assert llm.calls == ["key1", "key2"]
    # The exhausted key rests: the next request goes straight to the fallback.
    await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert llm.calls == ["key1", "key2", "key2"]


async def test_all_keys_over_quota_fails_fast():
    llm = make_llm([QUOTA], [QUOTA], deadline_s=5)
    started = asyncio.get_running_loop().time()
    with pytest.raises(RuntimeError):
        await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert asyncio.get_running_loop().time() - started < 0.5  # straight to the rule fallback
