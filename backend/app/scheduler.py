"""In-process cron scheduler (ARCHITECTURE.md §8, docs/phases/05-api-scheduler.md
step 5). One APScheduler job per user with a `schedule_cron`, re-synced
whenever `PUT /preferences` changes it. `scheduler` is a module-level
singleton (matches the FastAPI-lifespan-owned-scheduler pattern): the API
process is single-instance by design (docs/DECISIONS.md D-02), so one
BackgroundScheduler per process is exactly the seam ARCHITECTURE §8 already
documents as needing a DB advisory lock or a queue if that ever changes.
"""

import logging

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.db import session_scope
from app.models import EpisodeTrigger, Preferences, User
from app.pipeline.episodes import create_episode, has_episode_in_progress, recover_stuck_episodes
from app.pipeline.runner import run_episode

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


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
        if has_episode_in_progress(db, user_id):
            logger.info(
                "user %s already has an episode in progress, skipping scheduled run", user_id
            )
            return
        episode = create_episode(
            db, owner, focus=None, target_minutes=None, trigger=EpisodeTrigger.SCHEDULE
        )
        episode_id = episode.id

    run_episode(episode_id)


def sync_user_schedule(user_id: int, schedule_cron: str | None, timezone: str) -> None:
    """Re-registers (or removes) this user's job. Safe to call whether or not
    a job already exists -- `PUT /preferences` calls this unconditionally
    after every save, not just when schedule_cron actually changed."""
    job_id = _job_id(user_id)
    if not schedule_cron:
        try:
            scheduler.remove_job(job_id)
            logger.info("removed schedule for user %s", user_id)
        except JobLookupError:
            pass
        return

    trigger = CronTrigger.from_crontab(schedule_cron, timezone=timezone)
    scheduler.add_job(
        run_scheduled_episode, trigger=trigger, id=job_id, args=[user_id], replace_existing=True
    )
    logger.info("scheduled user %s: %r (%s)", user_id, schedule_cron, timezone)


def start_scheduler() -> None:
    """Called once from the FastAPI lifespan on startup: loads every user's
    saved schedule from the DB and registers it, then starts the scheduler
    thread. Idempotent so re-entering it (e.g. a second TestClient lifespan
    in the same process) is a no-op."""
    if scheduler.running:
        return
    with session_scope() as db:
        rows = db.execute(
            select(User.id, Preferences.schedule_cron, Preferences.timezone)
            .join(Preferences, Preferences.user_id == User.id)
            .where(Preferences.schedule_cron.is_not(None))
        ).all()
        for user_id, schedule_cron, timezone in rows:
            sync_user_schedule(user_id, schedule_cron, timezone)
    scheduler.start()
    logger.info("scheduler started with %d job(s)", len(scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def recover_stuck_episodes_now() -> int:
    """Startup recovery (docs/phases/05-api-scheduler.md step 6), called once
    from app.main's lifespan before the scheduler starts."""
    with session_scope() as db:
        return recover_stuck_episodes(db)
