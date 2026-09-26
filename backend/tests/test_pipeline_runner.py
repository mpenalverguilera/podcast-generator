import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Episode, EpisodeStatus, EpisodeTrigger, PipelineStep, StepStatus
from app.pipeline import STAGE_ORDER
from app.pipeline import voice as voice_stage
from app.pipeline.runner import _daily_spend_usd, _should_force_failure, run_episode
from tests.conftest import make_user_with_episode


def _steps_for(db, episode_id: int) -> list[PipelineStep]:
    db.expire_all()
    return list(
        db.scalars(
            select(PipelineStep)
            .where(PipelineStep.episode_id == episode_id)
            .order_by(PipelineStep.id)
        )
    )


def test_happy_path_reaches_ready(db) -> None:
    episode = make_user_with_episode(db)

    result = run_episode(episode.id)

    assert result.status == EpisodeStatus.READY
    assert result.ready_at is not None

    # scripting writes its own extra "grounding" row directly (it's a
    # sub-step, not a STAGE_ORDER stage -- docs/DECISIONS.md D-30), so there's
    # one more row than STAGE_ORDER stages.
    steps = _steps_for(db, episode.id)
    assert len(steps) == len(STAGE_ORDER) + 1
    assert all(s.status == StepStatus.SUCCESS for s in steps)
    stage_names = {s.stage for s in steps}
    assert stage_names == {status.value for status, _ in STAGE_ORDER} | {"grounding"}
    assert episode.grounding_flags_initial == []
    assert episode.grounding_flags_final == []


def test_resume_from_failed_stage(db) -> None:
    episode = make_user_with_episode(db)

    def _boom(_episode, _adapters, _db):
        raise RuntimeError("boom")

    # A scoped MonkeyPatch, not the `monkeypatch` fixture: that fixture instance
    # is shared with every other fixture in this test's dependency graph,
    # including conftest.py's autouse _fast_test_isolation (data_dir, the
    # no-op loudnorm filter) -- calling *its* .undo() mid-test to restore the
    # real voice stage below would also silently revert those, sending the
    # retry's audio into the real backend/data/ with the real (slow) filter.
    # This context manager undoes only its own patch, on exit.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(voice_stage, "run", _boom)
        result = run_episode(episode.id)

    assert result.status == EpisodeStatus.FAILED
    assert result.failed_stage == "voicing"
    assert result.error == "boom"

    steps = _steps_for(db, episode.id)
    assert {s.stage for s in steps} == {
        "planning",
        "fetching",
        "ranking",
        "extracting",
        "scripting",
        "grounding",
        "voicing",
    }
    assert steps[-1].stage == "voicing"
    assert all(s.status == StepStatus.SUCCESS for s in steps[:-1])
    assert steps[-1].status == StepStatus.FAILED

    # The context manager above already restored the real voice stage.
    result2 = run_episode(episode.id)
    assert result2.status == EpisodeStatus.READY

    steps2 = _steps_for(db, episode.id)
    # 7 rows from the first (failed) run (6 STAGE_ORDER stages up to the
    # failed voicing attempt, plus scripting's own extra "grounding" row) + 2
    # from the resume (voicing retried, then assembling) = 9. The retried
    # stage legitimately gets a second row (its failed attempt is a real,
    # billable event we keep); every stage before it was skipped, not
    # re-run, so it keeps exactly one row.
    assert len(steps2) == len(STAGE_ORDER) + 2
    stage_counts: dict[str, int] = {}
    for s in steps2:
        stage_counts[s.stage] = stage_counts.get(s.stage, 0) + 1
    assert stage_counts.pop("voicing") == 2
    assert all(count == 1 for count in stage_counts.values())


def test_logs_stage_entry_and_failure_at_error_level(db, monkeypatch, caplog) -> None:
    episode = make_user_with_episode(db)

    def _boom(_episode, _adapters, _db):
        raise RuntimeError("boom")

    monkeypatch.setattr(voice_stage, "run", _boom)

    with caplog.at_level(logging.INFO, logger="app.pipeline.runner"):
        run_episode(episode.id)

    entered_planning = any(
        r.levelno == logging.INFO and "entering stage planning" in r.message for r in caplog.records
    )
    assert entered_planning

    failure_records = [r for r in caplog.records if "stage voicing failed" in r.message]
    assert len(failure_records) == 1
    assert failure_records[0].levelno == logging.ERROR


class _ProcessKilled(BaseException):
    """Stands in for the process dying mid-stage: a BaseException, so the
    runner's `except Exception` doesn't turn it into a clean stage failure."""


def test_crash_mid_run_keeps_completed_stages(db, monkeypatch) -> None:
    """Each stage is committed as it completes (docs/DECISIONS.md D-37): a
    crash during voicing must leave the episode at voicing with every earlier
    stage's pipeline_steps row persisted, not rolled back to pending."""
    episode = make_user_with_episode(db)

    def _killed(*_args, **_kwargs):
        raise _ProcessKilled

    monkeypatch.setattr(voice_stage, "run", _killed)
    try:
        run_episode(episode.id)
    except _ProcessKilled:
        pass

    db.refresh(episode)
    assert episode.status == EpisodeStatus.VOICING
    assert {"planning", "fetching", "ranking", "extracting", "scripting"} <= {
        s.stage for s in _steps_for(db, episode.id)
    }


def test_stop_after_marks_the_pause(db) -> None:
    episode = make_user_with_episode(db)

    run_episode(episode.id, stop_after="planning")
    db.refresh(episode)
    assert (episode.status, episode.error) == (EpisodeStatus.FETCHING, "stopped after planning")

    run_episode(episode.id)
    db.refresh(episode)
    assert (episode.status, episode.error) == (EpisodeStatus.READY, None)


def test_fake_fail_once_at_fails_once_then_resumes(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "fake_fail_once_at", "ranking")
    episode = make_user_with_episode(db)

    first = run_episode(episode.id)
    assert (first.status, first.failed_stage) == (EpisodeStatus.FAILED, "ranking")
    assert "FAKE_FAIL_ONCE_AT" in first.error

    second = run_episode(episode.id)
    assert second.status == EpisodeStatus.READY


def test_fake_fail_once_at_is_ignored_with_real_tts(db, monkeypatch) -> None:
    """Never throws away a paid run: with real TTS the switch is off."""
    monkeypatch.setattr(get_settings(), "fake_fail_once_at", "ranking")
    episode = make_user_with_episode(db)

    assert _should_force_failure(db, episode.id, "ranking", "fake") is True
    assert _should_force_failure(db, episode.id, "ranking", "elevenlabs") is False
    assert _should_force_failure(db, episode.id, "voicing", "fake") is False


def test_daily_spend_ignores_synthetic_episodes(db) -> None:
    real = make_user_with_episode(db)
    seeded = Episode(
        user_id=real.user_id,
        status=EpisodeStatus.READY,
        trigger=EpisodeTrigger.SCHEDULE,
        window_start=datetime.now(UTC),
        target_minutes=6,
        is_synthetic=True,
    )
    db.add(seeded)
    db.flush()
    for episode_id, cost in ((real.id, 0.25), (seeded.id, 100.0)):
        db.add(
            PipelineStep(
                episode_id=episode_id,
                stage="voicing",
                status=StepStatus.SUCCESS,
                provider="elevenlabs",
                cost_usd=cost,
                started_at=datetime.now(UTC),
            )
        )
    db.commit()

    assert _daily_spend_usd(db, datetime.now(UTC).date()) == 0.25
