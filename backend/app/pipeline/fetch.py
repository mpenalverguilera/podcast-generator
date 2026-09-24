import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.adapters.search.protocol import SearchSource
from app.models import Article, ArticleScore, Episode
from app.schemas import PlannedQuery, RawArticle, Usage

logger = logging.getLogger(__name__)

_MIN_RESULTS_BEFORE_RETRY = 3
_FETCH_CONCURRENCY = 4


def normalize_url(url: str) -> str:
    """Lowercase host, strip utm_* query params and the fragment, drop a
    trailing slash -- so the same article found via different query strings
    or link-tracking params hashes to the same url_hash."""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, host, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def _in_window(article: RawArticle, since: datetime) -> bool:
    return article.published_at is None or article.published_at >= since


def search_with_retry(
    search: SearchSource, query: str, since: datetime
) -> tuple[list[RawArticle], list[Usage]]:
    """One planned query -> its candidate articles, retrying once without the
    date filter (keeping only in-window-or-undated results from the retry) if
    the first pass returned fewer than 3 results. Per docs/ARCHITECTURE.md
    5.2 / the exa-news-search skill."""
    articles, usage = search.search(query, since=since)
    usages = [usage]
    if len(articles) < _MIN_RESULTS_BEFORE_RETRY:
        retry_articles, retry_usage = search.search(query, since=None)
        usages.append(retry_usage)
        seen = {normalize_url(a.url) for a in articles}
        for a in retry_articles:
            key = normalize_url(a.url)
            if key not in seen and _in_window(a, since):
                articles.append(a)
                seen.add(key)
    return articles, usages


def _upsert_article(db: Session, raw: RawArticle) -> Article:
    h = url_hash(raw.url)
    article = db.scalar(select(Article).where(Article.url_hash == h))
    if article is None:
        article = Article(
            url_hash=h,
            url=raw.url,
            outlet=raw.outlet or urlsplit(raw.url).netloc,
            title=raw.title,
            published_at=raw.published_at,
            highlights=raw.highlights or None,
        )
        db.add(article)
        db.flush()
        return article

    # Keep the first-seen highlights; only fill in fields that were missing.
    if article.title is None and raw.title:
        article.title = raw.title
    if article.outlet is None and raw.outlet:
        article.outlet = raw.outlet
    if article.published_at is None and raw.published_at:
        article.published_at = raw.published_at
    if not article.highlights and raw.highlights:
        article.highlights = raw.highlights
    return article


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    planned = [PlannedQuery.model_validate(q) for q in (episode.planned_queries or [])]
    if not planned:
        logger.warning("episode %s has no planned queries; nothing to fetch", episode.id)
        return Usage(provider="exa", cost_is_estimate=False, usage_source="exact")

    # Network calls only happen inside the thread pool; every DB write happens
    # back on the main thread afterwards -- SQLAlchemy Sessions aren't thread-safe.
    results: dict[int, tuple[list[RawArticle], list[Usage]]] = {}
    with ThreadPoolExecutor(max_workers=_FETCH_CONCURRENCY) as pool:
        futures = {
            pool.submit(search_with_retry, adapters.search, q.query, episode.window_start): i
            for i, q in enumerate(planned)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    existing_scores = {
        (s.article_id, s.topic)
        for s in db.scalars(select(ArticleScore).where(ArticleScore.episode_id == episode.id))
    }
    linked_article_ids: set[int] = set()
    total_cost = 0.0
    total_seen = 0

    for i, q in enumerate(planned):
        articles, usages = results[i]
        total_cost += sum(u.cost_usd for u in usages)
        total_seen += len(articles)
        for raw in articles:
            article = _upsert_article(db, raw)
            linked_article_ids.add(article.id)
            key = (article.id, q.topic)
            if key in existing_scores:
                continue
            db.add(ArticleScore(episode_id=episode.id, article_id=article.id, topic=q.topic))
            existing_scores.add(key)

    logger.info(
        "episode %s fetch: %d queries, %d results seen, %d unique articles linked, cost=$%.4f",
        episode.id,
        len(planned),
        total_seen,
        len(linked_article_ids),
        total_cost,
    )
    return Usage(
        provider="exa",
        units_in=len(linked_article_ids),
        cost_usd=total_cost,
        cost_is_estimate=False,
        usage_source="exact",
    )
