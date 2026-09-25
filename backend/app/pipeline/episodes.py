"""Episode-creation logic shared by the CLI (`new-episode`/`generate`), the
API (`POST /episodes/generate`) and the scheduler (a cron-triggered run).
Previously lived only inline in app/cli.py's `_create_episode`; factored out
once the API and scheduler needed the exact same "resolve window +
target_minutes, create a pending episode" step, to avoid three copies."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Episode, EpisodeStatus, EpisodeTrigger, User

logger = logging.getLogger(__name__)

_STUCK_THRESHOLD_MINUTES = 30
_IN_PROGRESS_STATUSES = [
    s for s in EpisodeStatus if s not in (EpisodeStatus.READY, EpisodeStatus.FAILED)
]


def resolve_window_start(db: Session, owner: User) -> datetime:
    last_ready = db.scalar(
        select(Episode)
        .where(Episode.user_id == owner.id, Episode.status == EpisodeStatus.READY)
        .order_by(Episode.ready_at.desc())
        .limit(1)
    )
    return last_ready.ready_at if last_ready else datetime.now(UTC) - timedelta(days=7)


def has_episode_in_progress(db: Session, user_id: int) -> bool:
    return (
        db.scalar(
            select(Episode.id)
            .where(Episode.user_id == user_id, Episode.status.in_(_IN_PROGRESS_STATUSES))
            .limit(1)
        )
        is not None
    )


def create_episode(
    db: Session,
    owner: User,
    *,
    focus: str | None,
    target_minutes: int | None,
    trigger: EpisodeTrigger,
) -> Episode:
    """`target_minutes=None` uses the user's saved default (falling back to 6
    if preferences are somehow missing); a passed value is a one-off override
    for this episode only and never changes the saved default."""
    window_start = resolve_window_start(db, owner)
    resolved_minutes = target_minutes or (
        owner.preferences.target_minutes if owner.preferences else 6
    )

    episode = Episode(
        user_id=owner.id,
        status=EpisodeStatus.PENDING,
        trigger=trigger,
        focus_request=focus,
        window_start=window_start,
        target_minutes=resolved_minutes,
    )
    db.add(episode)
    db.flush()
    logger.info(
        "created episode %s for user %s (trigger=%s, window_start=%s, target_minutes=%s)",
        episode.id,
        owner.id,
        trigger.value,
        window_start.date(),
        resolved_minutes,
    )
    return episode


def recover_stuck_episodes(db: Session, threshold_minutes: int = _STUCK_THRESHOLD_MINUTES) -> int:
    """Startup recovery (docs/phases/05-api-scheduler.md step 6): an episode
    left in a running status when the process died (crash, restart, deploy)
    would otherwise sit unrunnable forever -- nothing re-triggers it, and the
    in-progress guard would block the user from starting a new one instead.
    Marking it failed lets a human (or a later `POST /retry`) resume it from
    `failed_stage`. Measured from `created_at`: a real episode finishes in
    minutes even with real TTS, so 30 minutes is generous headroom, not a
    figure worth tracking per-stage activity for.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
    stuck = db.scalars(
        select(Episode).where(
            Episode.status.in_(_IN_PROGRESS_STATUSES), Episode.created_at < cutoff
        )
    ).all()
    for episode in stuck:
        logger.warning(
            "episode %s stuck in status %s since %s, marking failed (interrupted)",
            episode.id,
            episode.status.value,
            episode.created_at,
        )
        episode.failed_stage = episode.status.value
        episode.status = EpisodeStatus.FAILED
        episode.error = "interrupted"
    return len(stuck)
