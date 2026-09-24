import logging

from sqlalchemy import select

from app.models import EpisodeStatus, PipelineStep, StepStatus
from app.pipeline import STAGE_ORDER
from app.pipeline import voice as voice_stage
from app.pipeline.runner import run_episode
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


def test_resume_from_failed_stage(db, monkeypatch) -> None:
    episode = make_user_with_episode(db)

    def _boom(_episode, _adapters, _db):
        raise RuntimeError("boom")

    monkeypatch.setattr(voice_stage, "run", _boom)

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

    # Undo the patch mid-test (not just at teardown) so the retry below uses
    # the real voice stage.
    monkeypatch.undo()

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
