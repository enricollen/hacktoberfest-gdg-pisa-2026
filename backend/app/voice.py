"""ElevenLabs: single-use tokens for browser-side realtime STT, and streamed TTS.

The browser streams the microphone straight to Scribe v2 Realtime (VAD commits) with a token
minted here, so the API key never leaves the server. Agent replies are synthesized with Flash
v2.5 and streamed back as MP3 so playback starts while audio is still being generated.
"""

import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from uuid import uuid4

from elevenlabs import AsyncElevenLabs

from app.config import Settings

log = logging.getLogger(__name__)


class Voice:
    def __init__(self, settings: Settings, max_utterances: int = 256) -> None:
        self.client = AsyncElevenLabs()  # reads ELEVENLABS_API_KEY
        self.settings = settings
        self._utterances: OrderedDict[str, str] = OrderedDict()
        self._max = max_utterances

    async def stt_token(self) -> str:
        started = time.perf_counter()
        try:
            response = await self.client.tokens.single_use.create("realtime_scribe")
        except Exception:
            log.exception("STT token request failed")
            raise
        log.info("STT token issued in %.0f ms", (time.perf_counter() - started) * 1000)
        return response.token

    def register(self, text: str) -> str:
        """Store an agent reply and return the id the browser uses to fetch its audio."""
        utterance_id = uuid4().hex
        self._utterances[utterance_id] = text
        while len(self._utterances) > self._max:
            self._utterances.popitem(last=False)
        return utterance_id

    def text_of(self, utterance_id: str) -> str | None:
        return self._utterances.get(utterance_id)

    async def stream(self, text: str, utterance_id: str) -> AsyncIterator[bytes]:
        """TTS audio chunks, logging time-to-first-byte, size and failures."""
        started = time.perf_counter()
        first_byte_ms: float | None = None
        size = 0
        try:
            async for chunk in self.client.text_to_speech.stream(
                self.settings.tts_voice_id,
                text=text,
                model_id=self.settings.tts_model,
                language_code=self.settings.tts_language,
                output_format=self.settings.tts_output_format,
            ):
                if first_byte_ms is None:
                    first_byte_ms = (time.perf_counter() - started) * 1000
                size += len(chunk)
                yield chunk
        except Exception as e:
            log.error(
                "TTS %s failed after %d bytes: %s",
                utterance_id[:8],
                size,
                getattr(e, "body", None) or repr(e),
            )
            raise
        log.info(
            "TTS %s: %d chars → %d KB, first byte %.0f ms, total %.0f ms",
            utterance_id[:8],
            len(text),
            size // 1024,
            first_byte_ms or -1,
            (time.perf_counter() - started) * 1000,
        )
