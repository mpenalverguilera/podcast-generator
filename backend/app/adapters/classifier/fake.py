from typing import TYPE_CHECKING

from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article


class FakeClassifier:
    """Deterministic Classifier for tests/CLI iteration: always returns a
    confident (not borderline) score, zero cost. 0.8 x 0.8 = 0.64 clears
    rank.py's 0.3 selection threshold even after recency decay, relying on
    FakeSearchSource keeping its fixture articles' published_at fresh
    (app/adapters/search/fake.py) -- a 0.5/0.5 "midpoint" default would
    silently fail every fake-pipeline test, since 0.5 x 0.5 = 0.25 never
    clears it."""

    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
    ) -> tuple[ArticleScoreResult, Usage]:
        result = ArticleScoreResult(
            topic=topic,
            relevance=0.8,
            newsworthy=0.8,
            already_covered=False,
            score=0.64,
        )
        usage = Usage(provider="fake", latency_ms=0, usage_source="fake")
        return result, usage
