"""Small pieces of per-episode context (the listener's profile, recent
headlines) shared by more than one pipeline stage (planner.py, rank.py)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Episode, EpisodeItem, EpisodeStatus, Preferences
from app.schemas import InterestProfile

_RECENT_EPISODES_FOR_HEADLINES = 2


def load_profile(db: Session, user_id: int) -> InterestProfile:
    prefs = db.get(Preferences, user_id)
    if prefs is None or not prefs.interest_profile:
        return InterestProfile()
    return InterestProfile.model_validate(prefs.interest_profile)


def recent_headlines(db: Session, episode: Episode) -> list[str]:
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
