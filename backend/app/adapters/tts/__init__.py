from app.adapters.tts.elevenlabs import ElevenLabsDialogueTTS
from app.adapters.tts.fake import FakeTTS
from app.adapters.tts.protocol import TTS
from app.config import Settings, get_settings


def get_tts(settings: Settings | None = None, override: str | None = None) -> TTS:
    settings = settings or get_settings()
    provider = override or settings.tts_provider
    if provider == "fake":
        return FakeTTS()
    if provider == "elevenlabs":
        return ElevenLabsDialogueTTS(settings)
    raise ValueError(f"unknown TTS provider {provider!r}")
