from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.llm.protocol import LLM
from app.config import Settings, get_settings
from app.prompts import load_prompt
from app.schemas import ArticleScoreResult, InterestProfile, Topic, Usage

if TYPE_CHECKING:
    from app.models import Article


def topic_for(profile: InterestProfile, topic: str) -> Topic:
    """Looks up the profile's own Topic for this name, so the prompt gets the
    user's include/exclude/description. The caller (rank.run) injects a
    synthetic "focus" Topic (description = the episode's focus_request) into
    the profile it passes in before scoring focus-tagged candidates, so that
    case is just a normal lookup here too. Falls back to an ad-hoc Topic only
    for a topic name the profile genuinely has no entry for (e.g. edited after
    this episode's candidates were fetched)."""
    match = next((t for t in profile.topics if t.name == topic), None)
    if match is not None:
        return match
    return Topic(name=topic, description=f"News about {topic}")


class LLMClassifier:
    """Real Classifier, composed from an LLM adapter (not a fresh OpenAI client)
    per ARCHITECTURE §6's "(wraps LLM)". Runtime prompt: the latest classifier.vN.md
    (v2, D-61: adds today's date and the episode window, and returns is_stale).

    `clock` returns "now"; it defaults to the real clock and exists so the eval can
    pin "today" to when its articles were actually fetched."""

    def __init__(
        self,
        llm: LLM,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._llm = llm
        self._settings = settings or get_settings()
        self._clock = clock or (lambda: datetime.now(UTC))

    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
        window_start: datetime,
    ) -> tuple[ArticleScoreResult, Usage]:
        t = topic_for(profile, topic)
        prompt = load_prompt(
            "classifier",
            topic_name=t.name,
            topic_description=t.description,
            topic_include=", ".join(t.include) or "none",
            topic_exclude=", ".join(t.exclude) or "none",
            avoid=", ".join(profile.avoid) or "none",
            title=article.title or "(no title)",
            outlet=article.outlet or "unknown",
            published_at=article.published_at.isoformat() if article.published_at else "unknown",
            highlights="\n".join(article.highlights or []) or "(no highlights)",
            recent_headlines="\n".join(f"- {h}" for h in recent_headlines) or "(none)",
            today=self._clock().date().isoformat(),
            window_start=window_start.date().isoformat(),
        )
        parsed, usage = self._llm.structured(
            prompt,
            ArticleScoreResult,
            model=self._settings.model_classifier,
            reasoning=self._settings.model_classifier_reasoning,
        )
        return parsed, usage
