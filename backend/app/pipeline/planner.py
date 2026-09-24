import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.config import get_settings
from app.models import Article, Episode, EpisodeItem, EpisodeStatus, Preferences
from app.prompts import load_prompt
from app.schemas import InterestProfile, QueryPlan, Usage

logger = logging.getLogger(__name__)

_RECENT_EPISODES_FOR_HEADLINES = 2


def _load_profile(db: Session, user_id: int) -> InterestProfile:
    prefs = db.get(Preferences, user_id)
    if prefs is None or not prefs.interest_profile:
        return InterestProfile()
    return InterestProfile.model_validate(prefs.interest_profile)


def _recent_headlines(db: Session, episode: Episode) -> list[str]:
    recent_episode_ids = db.scalars(
        select(Episode.id)
        .where(
            Episode.user_id == episode.user_id,
            Episode.status == EpisodeStatus.READY,
            Episode.id != episode.id,
        )
        .order_by(Episode.ready_at.desc())
        .limit(_RECENT_EPISODES_FOR_HEADLINES)
    ).all()
    if not recent_episode_ids:
        return []
    return list(
        db.scalars(
            select(Article.title)
            .join(EpisodeItem, EpisodeItem.article_id == Article.id)
            .where(EpisodeItem.episode_id.in_(recent_episode_ids), Article.title.is_not(None))
        )
    )


def _format_topics(profile: InterestProfile) -> str:
    if not profile.topics:
        return "(no topics yet)"
    lines = []
    for t in profile.topics:
        include = ", ".join(t.include) or "none"
        exclude = ", ".join(t.exclude) or "none"
        lines.append(
            f"- {t.name}: {t.description} "
            f"(depth: {t.depth}; include: {include}; exclude: {exclude})"
        )
    return "\n".join(lines)


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    profile = _load_profile(db, episode.user_id)
    recent_headlines = _recent_headlines(db, episode)

    prompt = load_prompt(
        "query_planner",
        topics=_format_topics(profile),
        avoid=", ".join(profile.avoid) or "none",
        focus_request=episode.focus_request or "(none)",
        window_description=f"since {episode.window_start.isoformat()}",
        recent_headlines="\n".join(f"- {h}" for h in recent_headlines) or "(no recent episodes)",
    )

    plan, usage = adapters.llm.structured(
        prompt, QueryPlan, model=settings.model_planner, reasoning="none"
    )

    episode.planned_queries = [q.model_dump() for q in plan.queries]
    episode.prompt_versions = {**(episode.prompt_versions or {}), prompt.name: prompt.version}
    logger.info(
        "episode %s planned %d queries (%d focus)",
        episode.id,
        len(plan.queries),
        sum(1 for q in plan.queries if q.is_focus),
    )
    return usage
