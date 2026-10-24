"""Gemma 4 on the Gemini API, returning validated Pydantic objects.

Gemma quirks (measured): `response_schema` → HTTP 500, `response_json_schema` works; thinking is
on by default and costs 10+ s, `thinking_level="minimal"` brings a reply to ~2 s.

The API is also erratic under load (random 500s, requests that hang, 2–12 s latency), so calls
are *hedged*: if the first request is slow a second one races it, a failed request is replaced
at once, and the first valid answer wins. Past the deadline callers get RuntimeError and must
fall back to deterministic logic.

Several API keys can be configured: a key that hits its quota (HTTP 429) rests for a minute and
requests move to the next one.
"""

import asyncio
import logging
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

QUOTA_COOLDOWN_S = 60.0  # free-tier quotas are per minute


class _Key:
    def __init__(self, api_key: str, label: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.label = label
        self.resting_until = 0.0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self.resting_until


class QuotaExhausted(Exception):
    """A key hit its quota (HTTP 429); retry on another key."""


class LLM:
    def __init__(
        self,
        api_keys: list[str],
        model: str,
        thinking_level: str,
        temperature: float,
        deadline_s: float = 20.0,
        hedge_after_s: float = 6.0,  # hedging doubles quota use: only for really slow calls
        max_parallel: int = 2,
        max_launches: int = 4,
    ) -> None:
        if not api_keys:
            raise ValueError("No Google API key configured (GOOGLE_API_KEY in backend/.env)")
        # Never log keys: label them by position and last 4 characters.
        self.keys = [_Key(k, f"key{i + 1}…{k[-4:]}") for i, k in enumerate(api_keys)]
        self._active = 0
        self.model = model
        self.thinking_level = thinking_level
        self.temperature = temperature
        self.deadline_s = deadline_s
        self.hedge_after_s = hedge_after_s
        self.max_parallel = max_parallel
        self.max_launches = max_launches

    def _key(self) -> _Key | None:
        """The active key if usable, else the next one not resting after a quota error."""
        for step in range(len(self.keys)):
            idx = (self._active + step) % len(self.keys)
            if self.keys[idx].available:
                if idx != self._active:
                    log.warning("switching Gemini API key → %s", self.keys[idx].label)
                    self._active = idx
                return self.keys[idx]
        return None

    async def _call[T: BaseModel](
        self, prompt: str, config: types.GenerateContentConfig, schema: type[T], n: int
    ) -> T:
        key = self._key()
        if key is None:
            raise QuotaExhausted("every API key is over quota")
        started = time.perf_counter()
        text = ""
        try:
            response = await key.client.aio.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
            text = response.text or ""
            result = schema.model_validate_json(text)
        except (errors.APIError, ValidationError) as e:
            log.warning(
                "%s request #%d (%s) failed after %.2fs: %s | raw=%r",
                schema.__name__,
                n,
                key.label,
                time.perf_counter() - started,
                str(e)[:200],
                text[:200],
            )
            if isinstance(e, errors.ClientError) and e.code == 429:
                key.resting_until = time.monotonic() + QUOTA_COOLDOWN_S
                log.warning("%s over quota: resting %.0fs", key.label, QUOTA_COOLDOWN_S)
                raise QuotaExhausted(key.label) from e
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
                    if isinstance(error, QuotaExhausted) and self._key() is None:
                        raise RuntimeError("LLM quota exhausted on every key") from error
                    if isinstance(error, errors.ClientError):  # other 4xx: retrying won't help
                        raise RuntimeError("LLM request rejected") from error
                    last_error = error
                if can_launch():  # replace the failed request straight away (next key on 429)
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
