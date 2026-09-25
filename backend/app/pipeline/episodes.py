"""Episode lifecycle logic shared by the CLI (`new-episode`/`generate`), the
API (`POST /episodes/generate`, `/retry`), the scheduler (a cron-triggered
run) and startup recovery: create a pending episode, resume a failed one,
start a run in the background, and recover episodes orphaned by a restart."""

import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    IN_PROGRESS_INDEX,
    Episode,
    EpisodeStatus,
    EpisodeTrigger,
    PipelineStep,
    StepStatus,
    User,
)
from app.pipeline import STAGE_ORDER
from app.pipeline.runner import STOPPED_AFTER, run_episode

logger = logging.getLogger(__name__)

_IN_PROGRESS_STATUSES = [
    s for s in EpisodeStatus if s not in (EpisodeStatus.READY, EpisodeStatus.FAILED)
]
INTERRUPTED = "interrupted"
# How many times startup recovery may automatically resume the same episode.
# Once is enough to survive a normal restart; more would turn an episode that
# itself crashes the process into a crash loop. docs/DECISIONS.md D-38.
_MAX_AUTO_RESUMES = 1


class EpisodeConflict(Exception):
    """The requested transition would break a rule: the user already has an
    episode in progress, or the episode isn't in a resumable state."""


def _is_in_progress_violation(exc: IntegrityError) -> bool:
    return IN_PROGRESS_INDEX in str(exc.orig)


def resolve_window_start(db: Session, owner: User) -> datetime:
    last_ready = db.scalar(
        select(Episode)
        .where(Episode.user_id == owner.id, Episode.status == EpisodeStatus.READY)
        .order_by(Episode.ready_at.desc())
        .limit(1)
    )
    return last_ready.ready_at if last_ready else datetime.now(UTC) - timedelta(days=7)


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
    for this episode only and never changes the saved default.

    Raises EpisodeConflict if the user already has an episode in progress --
    enforced by the partial unique index on `episodes`, so it holds even for
    two concurrent callers."""
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
    try:
        with db.begin_nested():
            db.add(episode)
            db.flush()
    except IntegrityError as exc:
        if _is_in_progress_violation(exc):
            raise EpisodeConflict("an episode is already in progress") from exc
        raise
    logger.info(
        "created episode %s for user %s (trigger=%s, window_start=%s, target_minutes=%s)",
        episode.id,
        owner.id,
        trigger.value,
        window_start.date(),
        resolved_minutes,
    )
    return episode


def _resume_status(failed_stage: str | None) -> EpisodeStatus:
    if not failed_stage or failed_stage == EpisodeStatus.PENDING.value:
        return STAGE_ORDER[0][0]  # failed before the first stage ran
    return EpisodeStatus(failed_stage)


def mark_resuming(db: Session, episode_id: int) -> EpisodeStatus:
    """Moves a failed episode back to the stage it failed in, so it counts as
    in progress again *before* any thread starts. A conditional UPDATE, not
    read-then-write: of two concurrent retries only one matches
    `status = 'failed'`; the other gets EpisodeConflict. The partial unique
    index likewise rejects the resume if another of the user's episodes is
    running. Returns the status the runner will start from."""
    failed_stage = db.scalar(select(Episode.failed_stage).where(Episode.id == episode_id))
    resume_at = _resume_status(failed_stage)
    try:
        with db.begin_nested():
            result = db.execute(
                update(Episode)
                .where(Episode.id == episode_id, Episode.status == EpisodeStatus.FAILED)
                .values(status=resume_at, failed_stage=None, error=None)
            )
    except IntegrityError as exc:
        if _is_in_progress_violation(exc):
            raise EpisodeConflict("another episode is already in progress") from exc
        raise
    if result.rowcount == 0:
        raise EpisodeConflict("episode is not in a failed state")
    return resume_at


def run_in_background(episode_id: int) -> None:
    """Background execution model (docs/DECISIONS.md D-34): a plain daemon
    thread, not FastAPI's BackgroundTasks or a task queue. The whole pipeline
    is one blocking call (network + local ffmpeg work), and this is a
    single-process app with no worker pool to hand it to (ARCHITECTURE §3/§8)
    -- a thread is the simplest thing that lets the caller return at once."""
    threading.Thread(target=run_episode, args=(episode_id,), daemon=True).start()


def recover_interrupted_episodes(db: Session) -> list[int]:
    """Startup recovery. The API is a single process (D-02) and runs are
    daemon threads inside it, so at boot *every* in-progress episode is an
    orphan: nothing will ever advance it, and it would block the user's
    Generate button (409) and their scheduled runs indefinitely. Each one is
    marked failed with error="interrupted" at the stage it was on, and a
    FAILED pipeline_steps row (provider="system") records the interruption --
    visible on the dashboard, and the counter that caps automatic resumes.

    Returns the ids that may be automatically resumed (interrupted at most
    _MAX_AUTO_RESUMES times so far). docs/DECISIONS.md D-38.

    Episodes paused with the CLI's `--stop-after` are marked failed (so they
    stop blocking the user) but never auto-resumed. Caveat: a CLI `generate`
    that is *actively running* while the API boots shares the DB and would be
    treated as interrupted too -- a dev-only situation."""
    orphans = db.scalars(select(Episode).where(Episode.status.in_(_IN_PROGRESS_STATUSES))).all()
    now = datetime.now(UTC)
    resumable = []
    for episode in orphans:
        stage = _resume_status(episode.status.value).value
        if episode.error and episode.error.startswith(STOPPED_AFTER):
            # A deliberate `--stop-after` pause, not a crash: unblock the
            # user (failed, retryable) but never resume it automatically.
            logger.info(
                "episode %s was %s, marking failed, not resuming", episode.id, episode.error
            )
            episode.status = EpisodeStatus.FAILED
            episode.failed_stage = stage
            continue
        logger.warning(
            "episode %s was in status %s when the process stopped, marking failed (interrupted)",
            episode.id,
            episode.status.value,
        )
        episode.status = EpisodeStatus.FAILED
        episode.failed_stage = stage
        episode.error = INTERRUPTED
        db.add(
            PipelineStep(
                episode_id=episode.id,
                stage=stage,
                status=StepStatus.FAILED,
                provider="system",
                started_at=now,
                finished_at=now,
                error=INTERRUPTED,
            )
        )
        db.flush()
        interruptions = db.scalar(
            select(func.count())
            .select_from(PipelineStep)
            .where(
                PipelineStep.episode_id == episode.id,
                PipelineStep.provider == "system",
                PipelineStep.error == INTERRUPTED,
            )
        )
        if interruptions <= _MAX_AUTO_RESUMES:
            resumable.append(episode.id)
        else:
            logger.warning(
                "episode %s interrupted %d times, not auto-resuming (retry manually)",
                episode.id,
                interruptions,
            )
    return resumable
