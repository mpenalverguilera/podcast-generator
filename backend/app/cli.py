from datetime import UTC, datetime, timedelta

import typer
from passlib.context import CryptContext
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import Episode, EpisodeStatus, EpisodeTrigger, PipelineStep, Preferences, User
from app.pipeline.runner import run_episode

cli = typer.Typer(help="Personal Podcast Generator pipeline CLI")
_pwd_context = CryptContext(schemes=["bcrypt"])


def _create_user_if_missing(db, email: str, password: str, is_admin: bool) -> None:
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        typer.echo(f"user {email} already exists (id={existing.id}), skipping")
        return

    settings = get_settings()
    user = User(
        email=email,
        password_hash=_pwd_context.hash(password),
        is_admin=is_admin,
        is_synthetic=False,
    )
    db.add(user)
    db.flush()
    db.add(
        Preferences(
            user_id=user.id,
            interest_profile={"topics": [], "avoid": []},
            target_minutes=6,
            host_a={"name": "Alex", "voice_id": settings.default_voice_host_a},
            host_b={"name": "Sam", "voice_id": settings.default_voice_host_b},
            timezone="UTC",
        )
    )
    typer.echo(f"created user {email} (id={user.id}, admin={is_admin})")


@cli.command("seed-users")
def seed_users() -> None:
    """Idempotently creates the admin and demo users from .env."""
    settings = get_settings()
    with session_scope() as db:
        _create_user_if_missing(
            db,
            settings.seed_admin_email,
            settings.seed_admin_password.get_secret_value(),
            is_admin=True,
        )
        _create_user_if_missing(
            db,
            settings.seed_user_email,
            settings.seed_user_password.get_secret_value(),
            is_admin=False,
        )


@cli.command("new-episode")
def new_episode(
    user: str = typer.Option(..., "--user", help="Email of the user to generate for"),
    focus: str | None = typer.Option(None, "--focus", help="Optional focus request"),
    minutes: int | None = typer.Option(None, "--minutes", help="Target length override"),
) -> None:
    with session_scope() as db:
        owner = db.scalar(select(User).where(User.email == user))
        if owner is None:
            typer.echo(f"no user with email {user!r}; run seed-users first", err=True)
            raise typer.Exit(code=1)

        last_ready = db.scalar(
            select(Episode)
            .where(Episode.user_id == owner.id, Episode.status == EpisodeStatus.READY)
            .order_by(Episode.ready_at.desc())
            .limit(1)
        )
        window_start = last_ready.ready_at if last_ready else datetime.now(UTC) - timedelta(days=7)
        target_minutes = minutes or (owner.preferences.target_minutes if owner.preferences else 6)

        episode = Episode(
            user_id=owner.id,
            status=EpisodeStatus.PENDING,
            trigger=EpisodeTrigger.MANUAL,
            focus_request=focus,
            window_start=window_start,
            target_minutes=target_minutes,
        )
        db.add(episode)
        db.flush()
        typer.echo(f"created episode {episode.id} for {user}")


@cli.command("run")
def run_cmd(
    episode_id: int = typer.Argument(..., help="Episode id to run"),
    stop_after: str | None = typer.Option(None, "--stop-after", help="Stage name to stop after"),
    tts: str | None = typer.Option(None, "--tts", help="Override TTS provider, e.g. 'fake'"),
) -> None:
    episode = run_episode(episode_id, stop_after=stop_after, tts_override=tts)
    if episode.status == EpisodeStatus.FAILED:
        typer.echo(
            f"episode {episode_id} failed at {episode.failed_stage}: {episode.error}", err=True
        )
        raise typer.Exit(code=1)
    typer.echo(f"episode {episode_id} status: {episode.status.value}")


@cli.command("show")
def show(episode_id: int = typer.Argument(..., help="Episode id to show")) -> None:
    with session_scope() as db:
        episode = db.get(Episode, episode_id)
        if episode is None:
            typer.echo(f"no episode with id {episode_id}", err=True)
            raise typer.Exit(code=1)

        typer.echo(
            f"episode {episode.id}: status={episode.status.value} "
            f"failed_stage={episode.failed_stage} error={episode.error} "
            f"title={episode.title!r} target_minutes={episode.target_minutes} "
            f"created_at={episode.created_at} ready_at={episode.ready_at}"
        )
        steps = db.scalars(
            select(PipelineStep)
            .where(PipelineStep.episode_id == episode.id)
            .order_by(PipelineStep.id)
        ).all()
        header = (
            f"{'stage':<12} {'status':<9} {'provider':<12} {'model':<14}"
            f" {'in':>7} {'out':>7} {'cost_usd':>10} {'est':>5} {'ms':>7}"
        )
        typer.echo(header)
        for step in steps:
            typer.echo(
                f"{step.stage:<12} {step.status.value:<9} {step.provider:<12} "
                f"{(step.model or ''):<14} {step.units_in or 0:>7} {step.units_out or 0:>7} "
                f"{float(step.cost_usd or 0):>10.4f} {str(step.cost_is_estimate):>5} "
                f"{step.latency_ms or 0:>7}"
            )


if __name__ == "__main__":
    cli()
