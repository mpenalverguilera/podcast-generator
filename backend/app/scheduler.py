"""In-process cron scheduler (ARCHITECTURE §8, docs/phases/05-api-scheduler.md
step 5). One APScheduler job per user with a `schedule_cron`, re-synced
whenever `PUT /preferences` changes it. `scheduler` is a module-level
singleton (matches the FastAPI-lifespan-owned-scheduler pattern): the API
process is single-instance by design (docs/DECISIONS.md D-02), so one
BackgroundScheduler per process is exactly the seam ARCHITECTURE §8 already
documents as needing a DB advisory lock or a queue if that ever changes.

Jobs live in memory only; what happens across a restart is in
docs/DECISIONS.md D-38 (boot recovery, auto-resume, one catch-up run).
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Episode, EpisodeTrigger, Preferences, User
from app.pipeline.episodes import (
    EpisodeConflict,
    create_episode,
    mark_resuming,
    recover_interrupted_episodes,
    run_in_background,
)
from app.pipeline.runner import run_episode

logger = logging.getLogger(__name__)

# APScheduler's default misfire_grace_time is 1 second: a run that fires
# late (laptop asleep at the scheduled time, scheduler thread stalled) is
# logged as "missed" and silently skipped. An hour of grace means a late run
# still happens, once (coalesce and max_instances=1 are already defaults).
scheduler = BackgroundScheduler(job_defaults={"misfire_grace_time": 3600})


def _job_id(user_id: int) -> str:
    return f"user-{user_id}"


def run_scheduled_episode(user_id: int) -> None:
    """The cron job body: create a pending episode (scheduled runs always use
    the user's saved default target_minutes, never an override) and run the
    whole pipeline synchronously on this APScheduler worker thread."""
    with session_scope() as db:
        owner = db.get(User, user_id)
        if owner is None:
            logger.warning("scheduled job for missing user %s, skipping", user_id)
            return
        try:
            episode = create_episode(
                db, owner, focus=None, target_minutes=None, trigger=EpisodeTrigger.SCHEDULE
            )
        except EpisodeConflict:
            logger.info(
                "user %s already has an episode in progress, skipping scheduled run", user_id
            )
            return
        episode_id = episode.id

    run_episode(episode_id)


def sync_user_schedule(
    user_id: int, schedule_cron: str | None, timezone: str, *, run_now: bool = False
) -> None:
    """Re-registers (or removes) this user's job. Safe to call whether or not
    a job already exists -- `PUT /preferences` calls this unconditionally
    after every save, not just when schedule_cron actually changed.
    `run_now=True` makes the job's first run immediate (the boot catch-up),
    after which it follows its cron as usual."""
    job_id = _job_id(user_id)
    if not schedule_cron:
        try:
            scheduler.remove_job(job_id)
            logger.info("removed schedule for user %s", user_id)
        except JobLookupError:
            pass
        return

    trigger = CronTrigger.from_crontab(schedule_cron, timezone=timezone)
    # Only pass next_run_time when needed: APScheduler reads an explicit
    # None as "paused", not "compute it from the trigger".
    extra = {"next_run_time": datetime.now(UTC)} if run_now else {}
    scheduler.add_job(
        run_scheduled_episode,
        trigger=trigger,
        id=job_id,
        args=[user_id],
        replace_existing=True,
        **extra,
    )
    logger.info(
        "scheduled user %s: %r (%s)%s",
        user_id,
        schedule_cron,
        timezone,
        ", catch-up run now" if run_now else "",
    )


def catch_up_due(
    db: Session, user_id: int, schedule_cron: str, timezone: str, now: datetime | None = None
) -> bool:
    """Did a scheduled run fall due while the process was down? The anchor is
    the last time a run happened (the user's newest scheduled episode) or the
    schedule was set (preferences.updated_at), whichever is later. If the
    first cron time after the anchor is already in the past, at least one run
    was missed. This is a yes/no, not a count: one catch-up episode covers the
    whole gap, because its news window starts at the last ready episode
    (resolve_window_start), so firing once per missed slot would only produce
    near-empty duplicates. docs/DECISIONS.md D-38."""
    now = now or datetime.now(UTC)
    last_scheduled = db.scalar(
        select(func.max(Episode.created_at)).where(
            Episode.user_id == user_id, Episode.trigger == EpisodeTrigger.SCHEDULE
        )
    )
    schedule_set_at = db.scalar(
        select(Preferences.updated_at).where(Preferences.user_id == user_id)
    )
    anchor = max(t for t in (last_scheduled, schedule_set_at) if t is not None)
    trigger = CronTrigger.from_crontab(schedule_cron, timezone=timezone)
    # get_next_fire_time includes its start instant; the run *at* the anchor
    # already happened, so look strictly after it.
    next_fire = trigger.get_next_fire_time(None, anchor + timedelta(seconds=1))
    return next_fire is not None and next_fire <= now


def start_scheduler() -> None:
    """Called once from the FastAPI lifespan on startup, after recovery:
    loads every user's saved schedule from the DB and registers it --
    immediately due if a run was missed while the process was down -- then
    starts the scheduler thread. Idempotent so re-entering it (e.g. a second
    TestClient lifespan in the same process) is a no-op."""
    if scheduler.running:
        return
    with session_scope() as db:
        rows = db.execute(
            select(User.id, Preferences.schedule_cron, Preferences.timezone)
            .join(Preferences, Preferences.user_id == User.id)
            .where(Preferences.schedule_cron.is_not(None))
        ).all()
        for user_id, schedule_cron, timezone in rows:
            run_now = catch_up_due(db, user_id, schedule_cron, timezone)
            sync_user_schedule(user_id, schedule_cron, timezone, run_now=run_now)
    scheduler.start()
    logger.info("scheduler started with %d job(s)", len(scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def recover_and_resume() -> int:
    """Startup recovery (docs/DECISIONS.md D-38), called once from app.main's
    lifespan before the scheduler starts: mark every orphaned episode failed
    ("interrupted"), then resume each one that hasn't already been
    auto-resumed, from the stage it was on. Each resume is committed before
    its thread starts, so a catch-up run for the same user sees it as in
    progress and skips. Returns how many were resumed."""
    with session_scope() as db:
        resumable = recover_interrupted_episodes(db)

    resumed = 0
    for episode_id in resumable:
        with session_scope() as db:
            try:
                mark_resuming(db, episode_id)
            except EpisodeConflict as exc:
                logger.warning("not auto-resuming episode %s: %s", episode_id, exc)
                continue
        logger.info("auto-resuming interrupted episode %s", episode_id)
        run_in_background(episode_id)
        resumed += 1
    return resumed
