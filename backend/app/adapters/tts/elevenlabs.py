import time

from elevenlabs.client import ElevenLabs

from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import Turn, Usage

_VOICE_BY_SPEAKER = {"host_a": "default_voice_host_a", "host_b": "default_voice_host_b"}


class ElevenLabsDialogueTTS:
    """Real TTS adapter. Call shape per .claude/skills/elevenlabs-dialogue and
    docs/DECISIONS.md D-12: must use with_raw_response.convert (a
    contextmanager) to read the character-cost header, since the plain
    .convert() return value is only audio bytes with nowhere for a cost number
    to live, and this key can't read account-level quota either."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.elevenlabs_api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set; cannot construct ElevenLabsDialogueTTS"
            )
        # api_key must be passed explicitly -- the SDK does not read it from env.
        self._client = ElevenLabs(api_key=settings.elevenlabs_api_key.get_secret_value())
        self._settings = settings

    def synthesize_chunk(self, turns: list[Turn], seed: int | None) -> tuple[bytes, Usage]:
        inputs = [
            {"text": t.text, "voice_id": getattr(self._settings, _VOICE_BY_SPEAKER[t.speaker])}
            for t in turns
        ]
        start = time.monotonic()
        with self._client.text_to_dialogue.with_raw_response.convert(
            inputs=inputs,
            model_id=self._settings.elevenlabs_model,
            output_format=self._settings.elevenlabs_output_format,
            seed=seed,
        ) as resp:
            headers = resp.headers
            audio_bytes = b"".join(resp.data)
        latency_ms = int((time.monotonic() - start) * 1000)

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
