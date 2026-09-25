from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Episode, EpisodeStatus, EpisodeTrigger, PipelineStep, Preferences, User
from app.pipeline.episodes import (
    EpisodeConflict,
    create_episode,
    mark_resuming,
    recover_interrupted_episodes,
    resolve_window_start,
)
from app.pipeline.runner import run_episode


def _make_user(db, target_minutes: int = 6) -> User:
    user = User(email="ep-test@example.com", password_hash="x", is_admin=False)
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, target_minutes=target_minutes))
    db.commit()
    db.refresh(user)
    return user


def test_resolve_window_start_defaults_to_seven_days_back(db) -> None:
    user = _make_user(db)
    window_start = resolve_window_start(db, user)
    assert (datetime.now(UTC) - window_start) > timedelta(days=6, hours=23)


def test_resolve_window_start_uses_last_ready_episode(db) -> None:
    user = _make_user(db)
    ready_at = datetime.now(UTC) - timedelta(days=1)
    db.add(
        Episode(
            user_id=user.id,
            status=EpisodeStatus.READY,
            trigger=EpisodeTrigger.MANUAL,
            window_start=datetime.now(UTC) - timedelta(days=8),
            target_minutes=6,
            ready_at=ready_at,
        )
    )
    db.commit()

    window_start = resolve_window_start(db, user)
    assert window_start == ready_at


def test_create_episode_uses_override_or_saved_default(db) -> None:
    user = _make_user(db, target_minutes=8)

    default_ep = create_episode(
        db, user, focus=None, target_minutes=None, trigger=EpisodeTrigger.MANUAL
    )
    assert default_ep.target_minutes == 8
    # Only one in-progress episode per user: finish the first before the second.
    default_ep.status = EpisodeStatus.READY
    default_ep.ready_at = datetime.now(UTC)
    db.flush()

    override_ep = create_episode(
        db, user, focus="quantum computing", target_minutes=4, trigger=EpisodeTrigger.MANUAL
    )
    assert override_ep.target_minutes == 4
    assert override_ep.focus_request == "quantum computing"

    db.commit()
    db.refresh(user.preferences)
    assert user.preferences.target_minutes == 8, "the override must not change the saved default"


def _episode(db, user: User, status: EpisodeStatus, **fields) -> Episode:
    episode = Episode(
        user_id=user.id,
        status=status,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC) - timedelta(days=1),
        target_minutes=6,
        **fields,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    return episode


def test_create_episode_conflicts_while_one_is_in_progress(db) -> None:
    user = _make_user(db)
    create_episode(db, user, focus=None, target_minutes=None, trigger=EpisodeTrigger.MANUAL)
    db.commit()

    with pytest.raises(EpisodeConflict):
        create_episode(db, user, focus=None, target_minutes=None, trigger=EpisodeTrigger.SCHEDULE)
    # The savepoint rollback leaves the session usable and the first episode intact.
    assert len(db.scalars(select(Episode).where(Episode.user_id == user.id)).all()) == 1


def test_mark_resuming_moves_failed_back_to_its_stage(db) -> None:
    user = _make_user(db)
    episode = _episode(
        db, user, EpisodeStatus.FAILED, failed_stage="scripting", error="provider timeout"
    )

    assert mark_resuming(db, episode.id) == EpisodeStatus.SCRIPTING
    db.commit()
    db.refresh(episode)
    assert (episode.status, episode.failed_stage, episode.error) == (
        EpisodeStatus.SCRIPTING,
        None,
        None,
    )

    # A second retry (double click) no longer matches status='failed'.
    with pytest.raises(EpisodeConflict, match="not in a failed state"):
        mark_resuming(db, episode.id)


def test_mark_resuming_conflicts_with_another_running_episode(db) -> None:
    user = _make_user(db)
    _episode(db, user, EpisodeStatus.VOICING)
    failed = _episode(db, user, EpisodeStatus.FAILED, failed_stage="planning")

    with pytest.raises(EpisodeConflict, match="already in progress"):
        mark_resuming(db, failed.id)
    db.refresh(failed)
    assert failed.status == EpisodeStatus.FAILED


def test_recover_marks_every_orphan_failed_regardless_of_age(db) -> None:
    user = _make_user(db)
    other = User(email="ep-test-2@example.com", password_hash="x", is_admin=False)
    db.add(other)
    db.commit()
    just_started = _episode(db, user, EpisodeStatus.VOICING)
    never_started = _episode(db, other, EpisodeStatus.PENDING)

    resumable = recover_interrupted_episodes(db)
    db.commit()

    assert sorted(resumable) == sorted([just_started.id, never_started.id])
    db.refresh(just_started)
    db.refresh(never_started)
    assert (just_started.status, just_started.failed_stage, just_started.error) == (
        EpisodeStatus.FAILED,
        "voicing",
        "interrupted",
    )
    # "pending" maps to the first real stage, so a retry can resume it.
    assert never_started.failed_stage == "planning"
    step = db.scalar(select(PipelineStep).where(PipelineStep.episode_id == just_started.id))
    assert (step.provider, step.status.value, step.error) == ("system", "failed", "interrupted")


def test_recover_offers_auto_resume_only_once(db) -> None:
    user = _make_user(db)
    episode = _episode(db, user, EpisodeStatus.SCRIPTING)

    assert recover_interrupted_episodes(db) == [episode.id]
    db.commit()
    mark_resuming(db, episode.id)  # auto-resumed, then the process dies again
    db.commit()

    assert recover_interrupted_episodes(db) == []
    db.commit()
    db.refresh(episode)
    assert episode.status == EpisodeStatus.FAILED, "still recovered, just not resumed again"


def test_recover_does_not_resume_a_stop_after_pause(db) -> None:
    user = _make_user(db)
    episode = _episode(db, user, EpisodeStatus.VOICING, error="stopped after scripting")

    assert recover_interrupted_episodes(db) == []
    db.commit()
    db.refresh(episode)
    assert (episode.status, episode.failed_stage) == (EpisodeStatus.FAILED, "voicing")
    assert db.scalar(select(PipelineStep).where(PipelineStep.episode_id == episode.id)) is None


def test_recovered_pending_episode_is_retryable_end_to_end(db) -> None:
    """Regression: recovery used to write failed_stage="pending", which the
    runner's resume logic rejected, so every interrupted-before-planning
    episode was unretryable."""
    user = _make_user(db)
    episode = _episode(db, user, EpisodeStatus.PENDING)
    recover_interrupted_episodes(db)
    db.commit()

    mark_resuming(db, episode.id)
    db.commit()
    result = run_episode(episode.id)
    assert result.status == EpisodeStatus.READY


def test_legacy_failed_stage_pending_still_runs(db) -> None:
    user = _make_user(db)
    episode = _episode(db, user, EpisodeStatus.FAILED, failed_stage="pending")
    assert run_episode(episode.id).status == EpisodeStatus.READY
