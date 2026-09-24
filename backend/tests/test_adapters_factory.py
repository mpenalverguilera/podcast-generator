from app.adapters.classifier import get_classifier
from app.adapters.classifier.fake import FakeClassifier
from app.adapters.classifier.openai import LLMClassifier
from app.adapters.llm import get_llm
from app.adapters.llm.fake import FakeLLM
from app.adapters.llm.openai import OpenAILLM
from app.adapters.search import get_search_source
from app.adapters.search.exa import ExaSource
from app.adapters.search.fake import FakeSearchSource
from app.adapters.tts import get_tts
from app.adapters.tts.elevenlabs import ElevenLabsDialogueTTS
from app.adapters.tts.fake import FakeTTS
from app.config import Settings

_REAL_KEYS = dict(
    openai_api_key="sk-test",
    elevenlabs_api_key="el-test",
    exa_api_key="exa-test",
)


def test_search_factory_respects_config() -> None:
    fake_settings = Settings(search_provider="fake")
    assert isinstance(get_search_source(fake_settings), FakeSearchSource)

    real_settings = Settings(search_provider="exa", **_REAL_KEYS)
    assert isinstance(get_search_source(real_settings), ExaSource)


def test_llm_factory_respects_config() -> None:
    fake_settings = Settings(llm_provider="fake")
    assert isinstance(get_llm(fake_settings), FakeLLM)

    real_settings = Settings(llm_provider="openai", **_REAL_KEYS)
    assert isinstance(get_llm(real_settings), OpenAILLM)


def test_classifier_factory_respects_config() -> None:
    fake_settings = Settings(classifier_provider="fake")
    assert isinstance(get_classifier(fake_settings), FakeClassifier)

    real_settings = Settings(classifier_provider="openai", **_REAL_KEYS)
    assert isinstance(get_classifier(real_settings), LLMClassifier)


def test_tts_factory_respects_config() -> None:
    fake_settings = Settings(tts_provider="fake")
    assert isinstance(get_tts(fake_settings), FakeTTS)

    real_settings = Settings(tts_provider="elevenlabs", **_REAL_KEYS)
    assert isinstance(get_tts(real_settings), ElevenLabsDialogueTTS)


def test_override_beats_settings() -> None:
    settings = Settings(tts_provider="elevenlabs", **_REAL_KEYS)
    assert isinstance(get_tts(settings, override="fake"), FakeTTS)
