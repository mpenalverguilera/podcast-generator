import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Article, ArticleScore, Episode, EpisodeItem
from app.pipeline.context import load_profile, recent_headlines
from app.schemas import ArticleScoreResult, InterestProfile, Topic, Usage

logger = logging.getLogger(__name__)

_MIN_SCORE = 0.3
_RECENCY_HALF_LIFE_DAYS = 3.0
_UNDATED_DECAY = 0.5
_MIN_STORY_COUNT = 3
_MINUTES_PER_STORY = 1.2
_CLASSIFY_CONCURRENCY = 8
_FOCUS_TOPIC = "focus"


@dataclass(frozen=True)
class Candidate:
    """The subset of an `article_scores` row rank.py's pure selection logic
    needs -- decoupled from the ORM so `select_stories` is unit-testable
    without a database."""

    article_id: int
    topic: str
    relevance: float
    newsworthy: float
    already_covered: bool
    published_at: datetime | None


@dataclass(frozen=True)
class Selected:
    article_id: int
    topic: str
    story_id: str
    position: int


def recency_decay(
    published_at: datetime | None, now: datetime, half_life_days: float = _RECENCY_HALF_LIFE_DAYS
) -> float:
    """1.0 for an article published in the future (clock skew); otherwise
    halves every `half_life_days`. An undated article gets `_UNDATED_DECAY`
    (one half-life old): fetch.py deliberately keeps undated results in the
    window, but an unknown publish date is a risk, not a signal of freshness,
    so it shouldn't score as if published this second. 0.5 still lets a
    strongly relevant undated article be selectable, but a dated, equally
    relevant one will now outrank it."""
    if published_at is None:
        return _UNDATED_DECAY
    age_days = (now - published_at).total_seconds() / 86400
    if age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


def story_count_for(target_minutes: int) -> int:
    return max(_MIN_STORY_COUNT, round(target_minutes / _MINUTES_PER_STORY))


def select_stories(
    candidates: list[Candidate], target_minutes: int, now: datetime
) -> list[Selected]:
    """Pure selection logic (docs/phases/03-pipeline.md step 1 / ARCHITECTURE
    §5.3): final = relevance x newsworthy x recency decay; drop already_covered
    and final < 0.3; per-topic cap for variety; one focus-request slot reserved
    first, opening the episode. Same-event collapsing is cut (D-22) -- this is
    the documented simple top-N-per-topic fallback.
    """
    story_count = story_count_for(target_minutes)
    per_topic_cap = math.ceil(story_count / 2)

    scored: list[tuple[float, Candidate]] = []
    for c in candidates:
        if c.already_covered:
            continue
        final = c.relevance * c.newsworthy * recency_decay(c.published_at, now)
        if final < _MIN_SCORE:
            continue
        scored.append((final, c))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    selected: list[Candidate] = []
    selected_article_ids: set[int] = set()
    per_topic_count: dict[str, int] = {}

    def _take(candidate: Candidate) -> None:
        selected.append(candidate)
        selected_article_ids.add(candidate.article_id)
        per_topic_count[candidate.topic] = per_topic_count.get(candidate.topic, 0) + 1

    focus_scored = [pair for pair in scored if pair[1].topic == _FOCUS_TOPIC]
    if focus_scored:
        _take(focus_scored[0][1])

    for _final, c in scored:
        if len(selected) >= story_count:
            break
        if c.article_id in selected_article_ids:
            continue
        if per_topic_count.get(c.topic, 0) >= per_topic_cap:
            continue
        _take(c)

    return [
        Selected(article_id=c.article_id, topic=c.topic, story_id=f"s{i + 1}", position=i)
        for i, c in enumerate(selected)
    ]


def _profile_for_topic(
    profile: InterestProfile, topic: str, focus_request: str | None
) -> InterestProfile:
    """Restricts the profile to the single topic being scored, so the
    classifier scores this (article, topic) row against exactly that topic
    rather than re-picking one. "focus" isn't a profile topic, so it's
    synthesized here from the episode's focus_request."""
    if topic == _FOCUS_TOPIC:
        focus_topic = Topic(
            name=_FOCUS_TOPIC, description=focus_request or "the listener's focus request"
        )
        return InterestProfile(topics=[focus_topic], avoid=profile.avoid)
    match = next((t for t in profile.topics if t.name == topic), None)
    topics = [match] if match else [Topic(name=topic, description=f"News about {topic}")]
    return InterestProfile(topics=topics, avoid=profile.avoid)


def _score_one(
    adapters: Adapters,
    article: Article,
    profile: InterestProfile,
    focus_request: str | None,
    topic: str,
    headlines: list[str],
) -> tuple[ArticleScoreResult, Usage]:
    topic_profile = _profile_for_topic(profile, topic, focus_request)
    return adapters.classifier.score(article, topic_profile, topic, headlines)


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    profile = load_profile(db, episode.user_id)
    headlines = recent_headlines(db, episode)

    rows = db.scalars(select(ArticleScore).where(ArticleScore.episode_id == episode.id)).all()
    if not rows:
        logger.warning("episode %s has no candidates to rank", episode.id)
        return Usage(provider="openai", cost_is_estimate=False, usage_source="exact")

    article_ids = {row.article_id for row in rows}
    articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(article_ids)))}

    # Classification is one independent LLM call per (article, topic) row, so
    # it's the same "network in a pool, DB writes on the main thread after"
    # shape as fetch.py's concurrent searches.
    with ThreadPoolExecutor(max_workers=_CLASSIFY_CONCURRENCY) as pool:
        futures = {
            pool.submit(
                _score_one,
                adapters,
                articles[row.article_id],
                profile,
                episode.focus_request,
                row.topic,
                headlines,
            ): row
            for row in rows
        }
        results: dict[int, tuple[ArticleScoreResult, Usage]] = {}
        for future in as_completed(futures):
            row = futures[future]
            results[row.id] = future.result()

    total_cost = 0.0
    total_latency = 0
    total_units_in = 0
    total_units_out = 0
    now = datetime.now(UTC)
    candidates: list[Candidate] = []

    for row in rows:
        result, usage = results[row.id]
        row.relevance = result.relevance
        row.newsworthy = result.newsworthy
        row.already_covered = result.already_covered
        row.same_event_as_url = result.same_event_as_url
        row.score = (
            result.relevance
            * result.newsworthy
            * recency_decay(articles[row.article_id].published_at, now)
        )
        row.classifier = usage.provider
        row.latency_ms = usage.latency_ms
        row.cost_usd = usage.cost_usd
        total_cost += usage.cost_usd
        total_latency = max(total_latency, usage.latency_ms)  # ran concurrently
        total_units_in += usage.units_in
        total_units_out += usage.units_out

        candidates.append(
            Candidate(
                article_id=row.article_id,
                topic=row.topic or "",
                relevance=result.relevance,
                newsworthy=result.newsworthy,
                already_covered=result.already_covered,
                published_at=articles[row.article_id].published_at,
            )
        )

    selected = select_stories(candidates, episode.target_minutes, now)

    # Idempotent on retry: a rank-stage failure after some rows were already
    # written (or a manual re-run) must not leave duplicate episode_items.
    db.execute(delete(EpisodeItem).where(EpisodeItem.episode_id == episode.id))
    for sel in selected:
        db.add(
            EpisodeItem(
                episode_id=episode.id,
                article_id=sel.article_id,
                position=sel.position,
                story_id=sel.story_id,
            )
        )
    db.flush()

    logger.info(
        "episode %s ranked %d candidates, selected %d stories, cost=$%.4f",
        episode.id,
        len(rows),
        len(selected),
        total_cost,
    )
    any_usage = next(iter(results.values()))[1]
    return Usage(
        provider=any_usage.provider,
        model=any_usage.model,
        units_in=total_units_in,
        units_out=total_units_out,
        cost_usd=total_cost,
        cost_is_estimate=any_usage.cost_is_estimate,
        latency_ms=total_latency,
        usage_source=any_usage.usage_source,
    )
