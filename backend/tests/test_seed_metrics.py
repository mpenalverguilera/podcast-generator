import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from typer.testing import CliRunner

from app import seed_metrics
from app.api.schemas import EventCreate
from app.cli import cli
from app.config import get_settings
from app.models import Episode, EpisodeStatus, Event, PipelineStep, Preferences, StepStatus, User
from app.schemas import InterestProfile, UnsupportedClaim

runner = CliRunner()
END = datetime(2026, 9, 1, tzinfo=UTC)
DAYS = 14


def _build(seed: int = 3, users: int = 10) -> list[seed_metrics.SeedUser]:
    settings = get_settings()
    return seed_metrics.build_dataset(
        random.Random(seed),
        days=DAYS,
        users=users,
        end=END,
        baselines=seed_metrics.fallback_baselines(settings),
        settings=settings,
        password_hash="x",
    )


def _counts(db) -> dict[str, int]:
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (User, Episode, PipelineStep, Event)
    }


def test_same_seed_gives_the_same_dataset() -> None:
    assert _build(seed=3) == _build(seed=3)
    assert _build(seed=3) != _build(seed=4)


def test_rows_are_synthetic_in_window_and_shaped_like_real_ones() -> None:
    dataset = _build(users=30)
    start = END - timedelta(days=DAYS)
    episodes = [ep for u in dataset for ep in u.episodes]
    assert episodes, "a 30-user, 14-day seed should produce episodes"

    for u in dataset:
        assert u.user["is_synthetic"] and u.user["email"].endswith("@synthetic.invalid")
        assert u.preferences["schedule_cron"] is None
        InterestProfile.model_validate(u.preferences["interest_profile"])
        for event in u.events:
            assert event["type"] == "login" and u.user["created_at"] <= event["created_at"] < END

    for ep in episodes:
        e = ep.episode
        assert e["is_synthetic"]
        assert e["status"] in (EpisodeStatus.READY, EpisodeStatus.FAILED)
        assert start <= e["created_at"] < END
        assert all(s["finished_at"] < END for s in ep.steps)
        for flag in (e["grounding_flags_initial"] or []) + (e["grounding_flags_final"] or []):
            UnsupportedClaim.model_validate(flag)
        if e["status"] == EpisodeStatus.FAILED:
            last = ep.steps[-1]
            assert last["status"] == StepStatus.FAILED and last["stage"] == e["failed_stage"]
            assert last["provider"] == "unknown" and last["cost_usd"] is None
        else:
            assert {s["stage"] for s in ep.steps} >= {"voicing", "grounding", "assembling"}
        for s in ep.steps:
            if s["provider"] == "elevenlabs":
                assert s["cost_is_estimate"]
        for event in ep.events:
            assert start <= event["created_at"] < END
            if event["type"] != "generate_clicked":
                EventCreate(type=event["type"], episode_id=1, payload=event["payload"] or {})


def test_seed_is_idempotent_and_reset_keeps_non_seed_rows(db) -> None:
    db.add(User(email="real@example.com", password_hash="x"))
    db.add(User(email="eval@example.com", password_hash="x", is_synthetic=True))
    db.commit()

    args = ["seed-metrics", "--days", str(DAYS), "--users", "10", "--seed", "3"]
    first = runner.invoke(cli, args)
    assert first.exit_code == 0, first.output
    after_first = _counts(db)
    assert after_first["users"] == 12
    assert db.scalar(select(func.count()).select_from(Preferences)) == 10

    second = runner.invoke(cli, args)
    assert second.exit_code == 0, second.output
    assert _counts(db) == after_first

    reset = runner.invoke(cli, ["seed-metrics", "--reset"])
    assert reset.exit_code == 0, reset.output
    remaining = db.scalars(select(User.email).order_by(User.email)).all()
    assert remaining == ["eval@example.com", "real@example.com"]
    assert _counts(db) == {"users": 2, "episodes": 0, "pipeline_steps": 0, "events": 0}
