from datetime import UTC, datetime

from app.adapters.classifier.openai import LLMClassifier
from app.adapters.llm import openai as openai_llm
from app.config import Settings
from app.models import Article
from app.schemas import ArticleScoreResult, InterestProfile, Topic, Usage


class _RecordingLLM:
    """LLM stub: records the prompt and call settings, returns a fixed stale result."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def structured(self, prompt, schema, model, reasoning):
        self.calls.append({"prompt": prompt, "model": model, "reasoning": reasoning})
        result = ArticleScoreResult(
            topic="Football", relevance=1.0, newsworthy=0.9, score=0.9, is_stale=True
        )
        return result, Usage(provider="fake", usage_source="fake")


def _article() -> Article:
    return Article(
        id=1,
        url_hash="h",
        url="u",
        title="Bayern beat Dortmund with ten rounds left",
        published_at=datetime(2026, 9, 26, tzinfo=UTC),
        highlights=["Ten rounds remain in the Bundesliga."],
    )


def test_classifier_uses_v2_prompt_with_today_window_and_reasoning_setting() -> None:
    llm = _RecordingLLM()
    settings = Settings(model_classifier="gpt-6-luna", model_classifier_reasoning="low")
    classifier = LLMClassifier(llm, settings, clock=lambda: datetime(2026, 9, 26, 17, tzinfo=UTC))
    profile = InterestProfile(topics=[Topic(name="Football", description="European football")])

    result, _ = classifier.score(
        _article(), profile, "Football", [], datetime(2026, 9, 19, 17, tzinfo=UTC)
    )

    call = llm.calls[0]
    assert call["prompt"].version == 2
    assert "Today is 2026-09-26. This episode covers news since 2026-09-19." in call["prompt"].text
    assert "is_stale" in call["prompt"].text
    assert call["model"] == "gpt-6-luna"
    assert call["reasoning"] == "low"
    assert result.is_stale is True


def test_openai_client_gets_timeout_setting_and_one_retry(monkeypatch) -> None:
    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(openai_llm, "OpenAI", _FakeOpenAI)
    openai_llm.OpenAILLM(Settings(openai_api_key="sk-test", openai_timeout_s=42))

    assert captured["timeout"] == 42
    assert captured["max_retries"] == 1


def test_openai_timeout_defaults_to_90_seconds() -> None:
    assert Settings.model_fields["openai_timeout_s"].default == 90.0
