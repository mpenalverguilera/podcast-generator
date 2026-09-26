"""Covers app/scheduler.py's job-management logic. The module-level scheduler
is started for this module only (never for the whole suite): an unstarted
BackgroundScheduler defers add_job/remove_job to an internal "pending jobs"
list that get_job() reads inconsistently (observed live -- a job removed
before start() still showed up in get_job() afterwards), so sync/removal are
only reliably testable against a running scheduler. Cron intervals here are
far enough out (daily/hourly) that nothing actually fires during the test."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Episode, EpisodeStatus, EpisodeTrigger, Preferences, User
from app.scheduler import catch_up_due, run_scheduled_episode, scheduler, sync_user_schedule


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


# A Sunday; the catch-up tests use a daily 08:00 UTC schedule around it.
_SUNDAY_8AM = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
_DAILY_8AM = "0 8 * * *"


def _scheduled_user(db, *, schedule_set_at: datetime, last_run_at: datetime | None) -> User:
    user = User(email="catchup@example.com", password_hash="x", is_admin=False)
    db.add(user)
    db.flush()
    db.add(
        Preferences(
            user_id=user.id, schedule_cron=_DAILY_8AM, timezone="UTC", updated_at=schedule_set_at
        )
    )
    if last_run_at is not None:
        db.add(
            Episode(
                user_id=user.id,
                status=EpisodeStatus.READY,
                trigger=EpisodeTrigger.SCHEDULE,
                window_start=last_run_at - timedelta(days=1),
                target_minutes=6,
                created_at=last_run_at,
            )
        )
    db.commit()
    return user


def test_catch_up_due_after_multi_day_downtime(db) -> None:
    """Down all Monday and Tuesday, back Wednesday 10:00: a run was missed,
    and the answer is a single yes (one catch-up), not one per missed day."""
    user = _scheduled_user(
        db, schedule_set_at=_SUNDAY_8AM - timedelta(days=7), last_run_at=_SUNDAY_8AM
    )
    wednesday_10am = _SUNDAY_8AM + timedelta(days=3, hours=2)
    assert catch_up_due(db, user.id, _DAILY_8AM, "UTC", now=wednesday_10am) is True


def test_catch_up_not_due_before_the_next_fire(db) -> None:
    user = _scheduled_user(
        db, schedule_set_at=_SUNDAY_8AM - timedelta(days=7), last_run_at=_SUNDAY_8AM
    )
    monday_7am = _SUNDAY_8AM + timedelta(hours=23)
    assert catch_up_due(db, user.id, _DAILY_8AM, "UTC", now=monday_7am) is False


def test_catch_up_anchors_on_schedule_change_when_never_run(db) -> None:
    """A schedule set Sunday 09:00 has not missed Sunday 08:00."""
    user = _scheduled_user(db, schedule_set_at=_SUNDAY_8AM + timedelta(hours=1), last_run_at=None)
    assert (
        catch_up_due(db, user.id, _DAILY_8AM, "UTC", now=_SUNDAY_8AM + timedelta(hours=2)) is False
    )
    assert (
        catch_up_due(db, user.id, _DAILY_8AM, "UTC", now=_SUNDAY_8AM + timedelta(days=1, hours=1))
        is True
    )


def test_run_scheduled_episode_skips_synthetic_users(db) -> None:
    user = User(email="seed@synthetic.invalid", password_hash="x", is_synthetic=True)
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, target_minutes=6, schedule_cron="0 * * * *"))
    db.commit()

    run_scheduled_episode(user.id)

    assert db.scalar(select(Episode).where(Episode.user_id == user.id)) is None
