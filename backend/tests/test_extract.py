from app.adapters import Adapters
from app.models import Article, ContentSource, EpisodeItem
from app.pipeline import extract
from app.schemas import ContentResult, Usage
from tests.conftest import make_user_with_episode


class _CountingSearchSource:
    """Records which URLs get_contents was asked for, so tests can assert
    extract.py never re-requests content the DB already has."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.calls: list[list[str]] = []
        self._texts = texts

    def search(self, query, since):  # pragma: no cover - unused by these tests
        raise NotImplementedError

    def get_contents(self, urls: list[str]):
        self.calls.append(list(urls))
        results = {}
        for url in urls:
            text = self._texts.get(url)
            if text is None:
                results[url] = ContentResult(url=url, text=None, status="error")
            else:
                results[url] = ContentResult(url=url, text=text, status="success")
        return results, Usage(provider="exa", cost_usd=0.01 * len(urls), cost_is_estimate=False)


def _add_article(db, *, url: str, content: str | None = None) -> Article:
    article = Article(
        url_hash=f"hash-{url}",
        url=url,
        title="Title",
        content=content,
        content_source=ContentSource.TEXT if content else ContentSource.HIGHLIGHTS,
    )
    db.add(article)
    db.flush()
    return article


def test_extract_skips_articles_that_already_have_content(db) -> None:
    episode = make_user_with_episode(db)
    cached = _add_article(db, url="https://example.com/cached", content="already have this")
    missing = _add_article(db, url="https://example.com/missing")
    db.add(EpisodeItem(episode_id=episode.id, article_id=cached.id, position=0, story_id="s1"))
    db.add(EpisodeItem(episode_id=episode.id, article_id=missing.id, position=1, story_id="s2"))
    db.flush()

    source = _CountingSearchSource({"https://example.com/missing": "fetched text"})
    adapters = Adapters(search=source, llm=None, classifier=None, tts=None)  # type: ignore[arg-type]

    usage = extract.run(episode, adapters, db)

    # Only the article missing content was ever requested from Exa.
    assert source.calls == [["https://example.com/missing"]]
    assert usage.cost_usd == 0.01

    db.refresh(cached)
    db.refresh(missing)
    assert cached.content == "already have this"  # untouched
    assert missing.content == "fetched text"
    assert missing.content_source == ContentSource.TEXT


def test_extract_makes_no_exa_call_when_everything_is_cached(db) -> None:
    episode = make_user_with_episode(db)
    cached = _add_article(db, url="https://example.com/cached", content="already have this")
    db.add(EpisodeItem(episode_id=episode.id, article_id=cached.id, position=0, story_id="s1"))
    db.flush()

    source = _CountingSearchSource({})
    adapters = Adapters(search=source, llm=None, classifier=None, tts=None)  # type: ignore[arg-type]

    usage = extract.run(episode, adapters, db)

    assert source.calls == []
    assert usage.cost_usd == 0.0


def test_extract_falls_back_to_highlights_on_error_status(db) -> None:
    episode = make_user_with_episode(db)
    article = _add_article(db, url="https://example.com/broken")
    db.add(EpisodeItem(episode_id=episode.id, article_id=article.id, position=0, story_id="s1"))
    db.flush()

    source = _CountingSearchSource({})  # no text for this url -> "error" status
    adapters = Adapters(search=source, llm=None, classifier=None, tts=None)  # type: ignore[arg-type]

    extract.run(episode, adapters, db)

    db.refresh(article)
    assert article.content is None
    assert article.content_source == ContentSource.HIGHLIGHTS


def test_extract_raises_when_ranking_selected_nothing(db) -> None:
    episode = make_user_with_episode(db)
    adapters = Adapters(search=_CountingSearchSource({}), llm=None, classifier=None, tts=None)  # type: ignore[arg-type]

    try:
        extract.run(episode, adapters, db)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
