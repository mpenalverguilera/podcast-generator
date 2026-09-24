from typing import TYPE_CHECKING

from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article


class FakeClassifier:
    """Deterministic Classifier for tests/CLI iteration: always returns a
    mid-range score, zero cost."""

    def score(
        self, article: "Article", profile: InterestProfile, recent_headlines: list[str]
    ) -> tuple[ArticleScoreResult, Usage]:
        result = ArticleScoreResult(
            topic=profile.topics[0].name if profile.topics else "general",
            relevance=0.5,
            newsworthy=0.5,
            already_covered=False,
            score=0.5,
        )
        usage = Usage(provider="fake", latency_ms=0, usage_source="fake")
        return result, usage
