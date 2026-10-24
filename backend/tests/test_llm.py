"""Hedged Gemma calls: hanging or failing requests must never block a turn."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.agent import prompts
from app.agent.llm import LLM

OK = '{"reply": "Ciao a tutti"}'
HANG = object()
FAIL = object()


def make_llm(responses, deadline_s=1.0):
    llm = LLM.__new__(LLM)
    llm.model, llm.thinking_level, llm.temperature = "m", "minimal", 0.7
    llm.deadline_s, llm.hedge_after_s, llm.max_parallel, llm.max_launches = deadline_s, 0.05, 2, 4
    calls = iter(responses)
    llm.calls = 0

    async def generate_content(**_):
        llm.calls += 1
        nxt = next(calls, HANG)
        if nxt is HANG:
            await asyncio.sleep(60)
        if nxt is FAIL:
            raise errors.ServerError(500, {"error": {"message": "Internal error"}})
        return SimpleNamespace(text=nxt, usage_metadata=None)

    llm.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    return llm


async def test_slow_request_is_hedged():
    llm = make_llm([HANG, OK])
    out = await llm.structured("sys", "prompt", prompts.ClosingOut)
    assert out.reply == "Ciao a tutti" and llm.calls == 2


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
