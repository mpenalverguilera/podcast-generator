from sqlalchemy import func, select
from typer.testing import CliRunner

from app.cli import cli
from app.models import Episode, EpisodeStatus, PipelineStep, User

runner = CliRunner()


def test_seed_users_is_idempotent(db) -> None:
    result1 = runner.invoke(cli, ["seed-users"])
    assert result1.exit_code == 0, result1.output

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User)) == 3

    result2 = runner.invoke(cli, ["seed-users"])
    assert result2.exit_code == 0, result2.output

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User)) == 3


def test_new_episode_and_run(db) -> None:
    seed_result = runner.invoke(cli, ["seed-users"])
    assert seed_result.exit_code == 0, seed_result.output

    db.expire_all()
    # is_admin=False now matches both the demo and eval users (seed-users
    # creates three), so narrow to the real (non-synthetic) demo account.
    demo_email = (
        db.scalars(select(User).where(User.is_admin.is_(False), User.is_synthetic.is_(False)))
        .one()
        .email
    )

    new_ep_result = runner.invoke(cli, ["new-episode", "--user", demo_email])
    assert new_ep_result.exit_code == 0, new_ep_result.output

    db.expire_all()
    episode = db.scalars(select(Episode).order_by(Episode.id.desc())).first()
    assert episode.status == EpisodeStatus.PENDING

    run_result = runner.invoke(cli, ["run", str(episode.id)])
    assert run_result.exit_code == 0, run_result.output

    db.expire_all()
    db.refresh(episode)
    assert episode.status == EpisodeStatus.READY

    show_result = runner.invoke(cli, ["show", str(episode.id)])
    assert show_result.exit_code == 0, show_result.output
    assert "ready" in show_result.output


def _demo_email(db) -> str:
    runner.invoke(cli, ["seed-users"])
    db.expire_all()
    return (
        db.scalars(select(User).where(User.is_admin.is_(False), User.is_synthetic.is_(False)))
        .one()
        .email
    )


def _latest_episode(db) -> Episode:
    db.expire_all()
    return db.scalars(select(Episode).order_by(Episode.id.desc())).first()


def _scripted_episode(db) -> Episode:
    """A fake-run episode paused after scripting, the way `generate
    --stop-after scripting` leaves it."""
    email = _demo_email(db)
    result = runner.invoke(cli, ["generate", "--user", email, "--stop-after", "scripting"])
    assert result.exit_code == 0, result.output
    return _latest_episode(db)


def test_rescript_rewrites_a_paused_episode_and_stops_before_voicing(db) -> None:
    episode = _scripted_episode(db)
    assert episode.status == EpisodeStatus.VOICING

    result = runner.invoke(cli, ["rescript", str(episode.id)])
    assert result.exit_code == 0, result.output

    db.expire_all()
    db.refresh(episode)
    assert episode.status == EpisodeStatus.VOICING
    assert episode.error.startswith("stopped after")
    assert episode.script["outline"] is not None
    stages = list(
        db.scalars(select(PipelineStep.stage).where(PipelineStep.episode_id == episode.id))
    )
    # Scripting ran twice; fetch and ranking once -- a rescript costs LLM calls only.
    assert stages.count("scripting") == 2
    assert stages.count("fetching") == 1 and stages.count("ranking") == 1


def test_rescript_refuses_a_ready_episode_without_force(db) -> None:
    episode = _scripted_episode(db)
    assert runner.invoke(cli, ["run", str(episode.id)]).exit_code == 0
    db.expire_all()
    db.refresh(episode)
    assert episode.status == EpisodeStatus.READY

    refused = runner.invoke(cli, ["rescript", str(episode.id)])
    assert refused.exit_code == 1
    assert "--force" in refused.output

    forced = runner.invoke(cli, ["rescript", str(episode.id), "--force"])
    assert forced.exit_code == 0, forced.output
    db.expire_all()
    db.refresh(episode)
    assert episode.status == EpisodeStatus.VOICING
    assert episode.audio_path is None


def test_rescript_refuses_an_episode_that_never_reached_scripting(db) -> None:
    runner.invoke(cli, ["new-episode", "--user", _demo_email(db)])
    episode = _latest_episode(db)

    result = runner.invoke(cli, ["rescript", str(episode.id)])
    assert result.exit_code == 1
    assert "pending" in result.output
