from app.adapters.llm.fake import FakeLLM
from app.adapters.llm.openai import OpenAILLM
from app.adapters.llm.protocol import LLM
from app.config import Settings, get_settings


def get_llm(settings: Settings | None = None, override: str | None = None) -> LLM:
    settings = settings or get_settings()
    provider = override or settings.llm_provider
    if provider == "fake":
        return FakeLLM()
    if provider == "openai":
        return OpenAILLM(settings)
    raise ValueError(f"unknown LLM provider {provider!r}")
