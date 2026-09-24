from sqlalchemy import func, select
from typer.testing import CliRunner

from app.cli import cli
from app.models import Episode, EpisodeStatus, User

runner = CliRunner()


def test_seed_users_is_idempotent(db) -> None:
    result1 = runner.invoke(cli, ["seed-users"])
    assert result1.exit_code == 0, result1.output

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User)) == 2

    result2 = runner.invoke(cli, ["seed-users"])
    assert result2.exit_code == 0, result2.output

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User)) == 2


def test_new_episode_and_run(db) -> None:
    seed_result = runner.invoke(cli, ["seed-users"])
    assert seed_result.exit_code == 0, seed_result.output

    db.expire_all()
    demo_email = db.scalars(select(User).where(User.is_admin.is_(False))).one().email

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
