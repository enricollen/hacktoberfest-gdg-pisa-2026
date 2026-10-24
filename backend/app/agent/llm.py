"""Gemma 4 on the Gemini API, returning validated Pydantic objects.

Gemma quirks (measured): `response_schema` → HTTP 500, `response_json_schema` works; thinking is
on by default and costs 10+ s, `thinking_level="minimal"` brings a reply to ~2 s.

The API is also erratic under load (random 500s, requests that hang, 2–12 s latency), so calls
are *hedged*: if the first request is slow a second one races it, a failed request is replaced
at once, and the first valid answer wins. Past the deadline callers get RuntimeError and must
fall back to deterministic logic.
"""

import asyncio
import logging
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)


class LLM:
    def __init__(
        self,
        model: str,
        thinking_level: str,
        temperature: float,
        deadline_s: float = 20.0,
        hedge_after_s: float = 6.0,  # hedging doubles quota use: only for really slow calls
        max_parallel: int = 2,
        max_launches: int = 4,
    ) -> None:
        self.client = genai.Client()  # reads GOOGLE_API_KEY
        self.model = model
        self.thinking_level = thinking_level
        self.temperature = temperature
        self.deadline_s = deadline_s
        self.hedge_after_s = hedge_after_s
        self.max_parallel = max_parallel
        self.max_launches = max_launches

    async def _call[T: BaseModel](
        self, prompt: str, config: types.GenerateContentConfig, schema: type[T], n: int
    ) -> T:
        started = time.perf_counter()
        text = ""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
            text = response.text or ""
            result = schema.model_validate_json(text)
        except (errors.APIError, ValidationError) as e:
            log.warning(
                "%s request #%d failed after %.2fs: %s | raw=%r",
                schema.__name__,
                n,
                time.perf_counter() - started,
                str(e)[:200],
                text[:200],
            )
            raise
        usage = response.usage_metadata
        log.info(
            "%s request #%d ok in %.2fs (tokens in=%s out=%s): %s",
            schema.__name__,
            n,
            time.perf_counter() - started,
            usage and usage.prompt_token_count,
            usage and usage.candidates_token_count,
            text[:600],
        )
        return result

    async def structured[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
            temperature=self.temperature,
        )
        deadline = time.monotonic() + self.deadline_s
        in_flight: set[asyncio.Task[T]] = set()
        launches = 0
        last_error: BaseException | None = None

        def launch() -> None:
            nonlocal launches
            launches += 1
            in_flight.add(asyncio.create_task(self._call(prompt, config, schema, launches)))

        def can_launch() -> bool:
            return launches < self.max_launches and len(in_flight) < self.max_parallel

        launch()
        try:
            while in_flight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                wait = min(remaining, self.hedge_after_s) if can_launch() else remaining
                done, _ = await asyncio.wait(
                    in_flight, timeout=wait, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    if can_launch():  # slow: race a second request against the first
                        log.info("%s slow after %.0fs, hedging", schema.__name__, wait)
                        launch()
                    continue
                for task in done:
                    in_flight.discard(task)
                    error = task.exception()
                    if error is None:
                        return task.result()
                    if isinstance(error, errors.ClientError):  # 4xx: retrying won't help
                        raise RuntimeError("LLM request rejected") from error
                    last_error = error
                if can_launch():  # replace the failed request straight away
                    launch()
        finally:
            for task in in_flight:
                task.cancel()
        log.error(
            "%s: no valid answer after %d requests in %.0fs",
            schema.__name__,
            launches,
            self.deadline_s,
        )
        raise RuntimeError("LLM unavailable") from last_error
