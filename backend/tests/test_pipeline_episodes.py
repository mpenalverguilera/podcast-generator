from datetime import UTC, datetime, timedelta

from app.models import Episode, EpisodeStatus, EpisodeTrigger, Preferences, User
from app.pipeline.episodes import (
    create_episode,
    has_episode_in_progress,
    recover_stuck_episodes,
    resolve_window_start,
)


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

    override_ep = create_episode(
        db, user, focus="quantum computing", target_minutes=4, trigger=EpisodeTrigger.MANUAL
    )
    assert override_ep.target_minutes == 4
    assert override_ep.focus_request == "quantum computing"

    db.commit()
    db.refresh(user.preferences)
    assert user.preferences.target_minutes == 8, "the override must not change the saved default"


def test_has_episode_in_progress(db) -> None:
    user = _make_user(db)
    assert has_episode_in_progress(db, user.id) is False

    create_episode(db, user, focus=None, target_minutes=None, trigger=EpisodeTrigger.MANUAL)
    db.commit()
    assert has_episode_in_progress(db, user.id) is True


def test_recover_stuck_episodes_marks_old_running_episodes_failed(db) -> None:
    user = _make_user(db)
    stuck = Episode(
        user_id=user.id,
        status=EpisodeStatus.VOICING,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
    )
    fresh = Episode(
        user_id=user.id,
        status=EpisodeStatus.PLANNING,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
    )
    db.add_all([stuck, fresh])
    db.commit()
    # created_at has a server_default of now(); backdate the stuck one directly.
    db.execute(
        Episode.__table__.update()
        .where(Episode.id == stuck.id)
        .values(created_at=datetime.now(UTC) - timedelta(minutes=45))
    )
    db.commit()

    recovered = recover_stuck_episodes(db)
    db.commit()

    assert recovered == 1
    db.refresh(stuck)
    db.refresh(fresh)
    assert stuck.status == EpisodeStatus.FAILED
    assert stuck.failed_stage == "voicing"
    assert stuck.error == "interrupted"
    assert fresh.status == EpisodeStatus.PLANNING
