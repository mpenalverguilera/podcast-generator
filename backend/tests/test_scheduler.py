"""Covers app/scheduler.py's job-management logic. The module-level scheduler
is started for this module only (never for the whole suite): an unstarted
BackgroundScheduler defers add_job/remove_job to an internal "pending jobs"
list that get_job() reads inconsistently (observed live -- a job removed
before start() still showed up in get_job() afterwards), so sync/removal are
only reliably testable against a running scheduler. Cron intervals here are
far enough out (daily/hourly) that nothing actually fires during the test."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Episode, EpisodeStatus, EpisodeTrigger, Preferences, User
from app.scheduler import run_scheduled_episode, scheduler, sync_user_schedule


@pytest.fixture(scope="module", autouse=True)
def _running_scheduler():
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


def test_sync_user_schedule_adds_and_updates_job() -> None:
    sync_user_schedule(user_id=999001, schedule_cron="0 8 * * *", timezone="UTC")
    job = scheduler.get_job("user-999001")
    assert job is not None

    sync_user_schedule(user_id=999001, schedule_cron="*/5 * * * *", timezone="UTC")
    job = scheduler.get_job("user-999001")
    assert job is not None  # replace_existing swapped the trigger, not a new job

    sync_user_schedule(user_id=999001, schedule_cron=None, timezone="UTC")
    assert scheduler.get_job("user-999001") is None


def test_sync_user_schedule_remove_is_a_noop_when_no_job_exists() -> None:
    sync_user_schedule(user_id=999002, schedule_cron=None, timezone="UTC")  # must not raise
    assert scheduler.get_job("user-999002") is None


def test_run_scheduled_episode_creates_and_runs_an_episode(db) -> None:
    user = User(email="scheduled@example.com", password_hash="x", is_admin=False)
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, target_minutes=6, schedule_cron="0 * * * *"))
    db.commit()

    run_scheduled_episode(user.id)

    episode = db.scalar(
        select(Episode)
        .where(Episode.user_id == user.id, Episode.trigger == EpisodeTrigger.SCHEDULE)
        .order_by(Episode.id.desc())
    )
    assert episode is not None
    assert episode.status == EpisodeStatus.READY


def test_run_scheduled_episode_skips_when_one_is_in_progress(db) -> None:
    user = User(email="scheduled-busy@example.com", password_hash="x", is_admin=False)
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, target_minutes=6))
    db.add(
        Episode(
            user_id=user.id,
            status=EpisodeStatus.SCRIPTING,
            trigger=EpisodeTrigger.MANUAL,
            window_start=datetime.now(UTC),
            target_minutes=6,
        )
    )
    db.commit()

    run_scheduled_episode(user.id)

    scheduled_episode_id = db.scalar(
        select(Episode.id).where(
            Episode.user_id == user.id, Episode.trigger == EpisodeTrigger.SCHEDULE
        )
    )
    assert scheduled_episode_id is None, "a scheduled run must not start while one is in progress"
