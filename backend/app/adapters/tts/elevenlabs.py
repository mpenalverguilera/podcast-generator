import logging
import random
import threading
import time

import httpx
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import Turn, Usage

logger = logging.getLogger(__name__)

_BACKOFF_BASE_S = 2.0
_MAX_RETRY_AFTER_S = 30.0

# ElevenLabs' concurrency limit is per account, and each episode run builds its
# own adapter (and several episodes can voice at once, D-34), so the cap on
# requests in flight must be process-wide, not per adapter or per voice stage.
_slots_lock = threading.Lock()
_slots: dict[int, threading.BoundedSemaphore] = {}


def _request_slots(limit: int) -> threading.BoundedSemaphore:
    with _slots_lock:
        return _slots.setdefault(limit, threading.BoundedSemaphore(limit))


def _is_retryable(exc: Exception) -> bool:
    """429 (too_many_concurrent_requests / system_busy) and 5xx produce no
    audio, so a retry can't double-bill. A connect error never reached the
    server. Anything else (401 incl. quota_exceeded, 422, a read timeout that
    may have been billed) fails at once."""
    if isinstance(exc, ApiError):
        return exc.status_code == 429 or (exc.status_code or 0) >= 500
    return isinstance(exc, httpx.ConnectError)


def _retry_wait_s(exc: Exception, attempt: int) -> float:
    headers = exc.headers if isinstance(exc, ApiError) else None
    retry_after = (headers or {}).get("retry-after")
    if retry_after is not None:
        try:
            return min(float(retry_after), _MAX_RETRY_AFTER_S)
        except ValueError:
            pass
    # Jitter so workers that hit a 429 together don't all come back at once.
    return _BACKOFF_BASE_S * 2 ** (attempt - 1) * random.uniform(0.75, 1.25)


class ElevenLabsDialogueTTS:
    """Real TTS adapter. Call shape per .claude/skills/elevenlabs-dialogue and
    docs/DECISIONS.md D-12: must use with_raw_response.convert (a
    contextmanager) to read the character-cost header, since the plain
    .convert() return value is only audio bytes with nowhere for a cost number
    to live, and this key can't read account-level quota either.

    Thread-safe: the voice stage calls synthesize_chunk from several workers on
    one instance; the SDK's underlying httpx.Client is safe to share (D-56)."""

    provider = "elevenlabs"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.elevenlabs_api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set; cannot construct ElevenLabsDialogueTTS"
            )
        # api_key must be passed explicitly -- the SDK does not read it from env.
        self._client = ElevenLabs(api_key=settings.elevenlabs_api_key.get_secret_value())
        self._settings = settings

    def _convert(self, inputs: list[dict], seed: int | None) -> tuple[bytes, dict[str, str]]:
        with self._client.text_to_dialogue.with_raw_response.convert(
            inputs=inputs,
            model_id=self._settings.elevenlabs_model,
            output_format=self._settings.elevenlabs_output_format,
            seed=seed,
        ) as resp:
            return b"".join(resp.data), resp.headers

    def synthesize_chunk(
        self, turns: list[Turn], seed: int | None, voices: dict[str, str]
    ) -> tuple[bytes, Usage]:
        inputs = [{"text": t.text, "voice_id": voices[t.speaker]} for t in turns]
        # The SDK retries 429/5xx only on non-streaming calls; text_to_dialogue
        # streams, so without this loop one 429 would fail the whole stage.
        max_attempts = self._settings.elevenlabs_max_attempts
        slots = _request_slots(self._settings.elevenlabs_max_concurrency)
        for attempt in range(1, max_attempts + 1):
            try:
                # Held only for the request itself, never during a backoff sleep.
                with slots:
                    start = time.monotonic()
                    audio_bytes, headers = self._convert(inputs, seed)
                break
            except Exception as exc:
                if attempt == max_attempts or not _is_retryable(exc):
                    raise
                wait_s = _retry_wait_s(exc, attempt)
                logger.warning(
                    "elevenlabs %s on attempt %d/%d, retrying in %.1fs",
                    getattr(exc, "status_code", type(exc).__name__),
                    attempt,
                    max_attempts,
                    wait_s,
                )
                time.sleep(wait_s)
        latency_ms = int((time.monotonic() - start) * 1000)

        logger.debug(
            "elevenlabs chunk done in %dms, concurrent requests %s/%s",
            latency_ms,
            headers.get("current-concurrent-requests"),
            headers.get("maximum-concurrent-requests"),
        )

        character_cost = headers.get("character-cost")
        if character_cost is not None:
            units_in = int(character_cost)
            usage_source = "header"
        else:
            units_in = sum(len(t.text) for t in turns)
            usage_source = "estimated"

        cost_usd, is_estimate = cost_for("elevenlabs", self._settings.elevenlabs_model, units_in)
        usage = Usage(
            provider="elevenlabs",
            model=self._settings.elevenlabs_model,
            units_in=units_in,
            cost_usd=cost_usd,
            cost_is_estimate=is_estimate,
            latency_ms=latency_ms,
            request_id=headers.get("request-id"),
            usage_source=usage_source,
        )
        return audio_bytes, usage
