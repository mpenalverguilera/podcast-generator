from datetime import UTC, datetime, timedelta

from app.adapters import Adapters
from app.adapters.search.fake import FakeSearchSource
from app.models import ArticleScore
from app.pipeline import fetch
from app.schemas import RawArticle, Usage
from tests.conftest import make_user_with_episode


def test_normalize_url_dedupes_utm_fragment_and_trailing_slash() -> None:
    variants = [
        "https://Example.com/story/",
        "https://example.com/story?utm_source=newsletter&utm_medium=email",
        "https://example.com/story#section-2",
        "https://example.com/story",
    ]
    hashes = {fetch.url_hash(u) for u in variants}
    assert len(hashes) == 1


def test_normalize_url_keeps_non_utm_query_params() -> None:
    a = fetch.url_hash("https://example.com/story?id=42")
    b = fetch.url_hash("https://example.com/story?id=43")
    assert a != b


class _StubSearchSource:
    """Returns too few results on the first (date-filtered) call, more on the
    retry (unfiltered) call, so search_with_retry's retry path is exercised
    deterministically -- FakeSearchSource always returns the same 10-result
    fixture regardless of `since`, so it can't exercise this branch."""

    def __init__(self, window_start: datetime) -> None:
        self.calls: list[datetime | None] = []
        self._window_start = window_start

    def search(self, query: str, since: datetime | None) -> tuple[list[RawArticle], Usage]:
        self.calls.append(since)
        if since is not None:
            return (
                [RawArticle(url="https://example.com/in-window", published_at=self._window_start)],
                Usage(provider="fake", cost_usd=0.01),
            )
        return (
            [
                RawArticle(url="https://example.com/in-window", published_at=self._window_start),
                RawArticle(
                    url="https://example.com/undated",
                    published_at=None,
                ),
                RawArticle(
                    url="https://example.com/stale",
                    published_at=self._window_start - timedelta(days=30),
                ),
            ],
            Usage(provider="fake", cost_usd=0.01),
        )

    def get_contents(self, urls):  # pragma: no cover - unused by these tests
        raise NotImplementedError


def test_search_with_retry_triggers_on_few_results_and_filters_by_window() -> None:
    window_start = datetime.now(UTC) - timedelta(days=7)
    source = _StubSearchSource(window_start)

    articles, usages = fetch.search_with_retry(source, "some query", window_start)

    assert source.calls == [window_start, None]
    assert len(usages) == 2
    urls = {a.url for a in articles}
    # The in-window story (deduped, not doubled) and the undated story are
    # kept; the stale one (published before the window) is dropped.
    assert urls == {"https://example.com/in-window", "https://example.com/undated"}


def test_search_with_retry_skips_retry_when_enough_results() -> None:
    class _AlwaysEnough:
        def search(self, query, since):
            return (
                [RawArticle(url=f"https://example.com/{i}") for i in range(5)],
                Usage(provider="fake", cost_usd=0.01),
            )

        def get_contents(self, urls):
            raise NotImplementedError

    source = _AlwaysEnough()
    articles, usages = fetch.search_with_retry(source, "q", datetime.now(UTC))

    assert len(articles) == 5
    assert len(usages) == 1


def test_run_links_candidates_and_dedupes_by_article_and_topic(db) -> None:
    episode = make_user_with_episode(db)
    episode.planned_queries = [
        {"topic": "AI", "query": "ai news", "is_focus": False},
        {"topic": "AI", "query": "more ai news", "is_focus": False},
        {"topic": "F1", "query": "f1 news", "is_focus": False},
    ]
    db.flush()

    adapters = Adapters(search=FakeSearchSource(), llm=None, classifier=None, tts=None)  # type: ignore[arg-type]
    usage = fetch.run(episode, adapters, db)

    assert usage.provider == "fake"
    assert usage.cost_is_estimate is False

    scores = db.query(ArticleScore).filter(ArticleScore.episode_id == episode.id).all()
    # FakeSearchSource always returns the same 10-article fixture: 2 "AI"
    # queries must collapse to one score row per article+topic, while the
    # distinct "F1" topic gets its own set of rows.
    assert {s.article_id for s in scores if s.topic == "AI"} == {
        s.article_id for s in scores if s.topic == "F1"
    }
    assert len({(s.article_id, s.topic) for s in scores}) == len(scores)
    assert usage.units_in == len({s.article_id for s in scores})


def test_run_with_no_planned_queries_returns_zero_cost(db) -> None:
    episode = make_user_with_episode(db)
    episode.planned_queries = []
    db.flush()

    adapters = Adapters(search=FakeSearchSource(), llm=None, classifier=None, tts=None)  # type: ignore[arg-type]
    usage = fetch.run(episode, adapters, db)

    assert usage.provider == "fake"
    assert usage.cost_usd == 0.0
