from app.adapters.classifier.fallback import FallbackClassifier
from app.models import Article
from app.schemas import ArticleScoreResult, InterestProfile, Topic, Usage


class _StubClassifier:
    """A Classifier stub: returns a fixed (result, usage) pair, or raises a fixed exception
    if one is given. Records every call for the test to assert against."""

    def __init__(self, *, result=None, usage=None, raises: Exception | None = None) -> None:
        self._result = result
        self._usage = usage
        self._raises = raises
        self.calls = 0

    def score(self, article, profile, topic, recent_headlines):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._result, self._usage


def _profile() -> InterestProfile:
    return InterestProfile(topics=[Topic(name="Space", description="space news")])


def _article() -> Article:
    return Article(id=1, url_hash="h", url="u", title="A rocket launched")


def _score_result(relevance: float) -> ArticleScoreResult:
    return ArticleScoreResult(
        topic="Space", relevance=relevance, newsworthy=0.9, score=relevance * 0.9
    )


def test_primary_success_never_calls_fallback() -> None:
    primary = _StubClassifier(result=_score_result(0.9), usage=Usage(provider="vercel_gateway"))
    fallback = _StubClassifier(result=_score_result(0.5), usage=Usage(provider="openai"))
    classifier = FallbackClassifier(primary, fallback)

    result, usage = classifier.score(_article(), _profile(), "Space", [])

    assert result.relevance == 0.9
    assert usage.provider == "vercel_gateway"
    assert usage.fallback_count == 0
    assert primary.calls == 1
    assert fallback.calls == 0


def test_primary_exception_falls_back_and_counts_it() -> None:
    """D-41: any exception from the primary (timeout, HTTP error, malformed response) falls
    back to Luna for that one article, and the returned Usage records that it happened."""
    primary = _StubClassifier(raises=TimeoutError("jev timed out"))
    fallback = _StubClassifier(result=_score_result(0.5), usage=Usage(provider="openai"))
    classifier = FallbackClassifier(primary, fallback)

    result, usage = classifier.score(_article(), _profile(), "Space", [])

    assert result.relevance == 0.5
    assert usage.provider == "openai"
    assert usage.fallback_count == 1
    assert primary.calls == 1
    assert fallback.calls == 1


def test_fallback_preserves_fallback_classifiers_own_usage_fields() -> None:
    """fallback_count=1 is added on top of the fallback classifier's own Usage, not a
    replacement -- cost/latency/model still come from whichever classifier actually ran."""
    primary = _StubClassifier(raises=RuntimeError("malformed response"))
    fallback_usage = Usage(provider="openai", model="gpt-6-luna", cost_usd=0.001, latency_ms=200)
    fallback = _StubClassifier(result=_score_result(0.5), usage=fallback_usage)
    classifier = FallbackClassifier(primary, fallback)

    _, usage = classifier.score(_article(), _profile(), "Space", [])

    assert usage.model == "gpt-6-luna"
    assert usage.cost_usd == 0.001
    assert usage.latency_ms == 200
    assert usage.fallback_count == 1
