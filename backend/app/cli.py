import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from passlib.context import CryptContext
from sqlalchemy import func, select

from app.adapters.llm import get_llm
from app.config import get_settings
from app.db import session_scope
from app.logging_setup import configure_logging
from app.models import (
    Article,
    ArticleScore,
    Episode,
    EpisodeStatus,
    EpisodeTrigger,
    PipelineStep,
    Preferences,
    User,
)
from app.pipeline.profile import extract_profile
from app.pipeline.runner import run_episode
from app.pipeline.script import strip_audio_tags
from app.schemas import Script

cli = typer.Typer(help="Personal Podcast Generator pipeline CLI")
_pwd_context = CryptContext(schemes=["bcrypt"])
logger = logging.getLogger(__name__)


@cli.callback()
def _main(ctx: typer.Context) -> None:
    configure_logging(get_settings().log_level)
    if ctx.invoked_subcommand:
        # Command name only -- never arguments, which can carry emails or
        # (via --answers file paths, --focus text) other user-entered data.
        logger.info("cli: %s", ctx.invoked_subcommand)


def _create_user_if_missing(
    db, email: str, password: str, is_admin: bool, is_synthetic: bool = False
) -> None:
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        logger.info("user %s already exists (id=%s), skipping", email, existing.id)
        typer.echo(f"user {email} already exists (id={existing.id}), skipping")
        return

    logger.info("creating user %s (admin=%s, synthetic=%s)", email, is_admin, is_synthetic)
    settings = get_settings()
    user = User(
        email=email,
        password_hash=_pwd_context.hash(password),
        is_admin=is_admin,
        is_synthetic=is_synthetic,
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
    """Idempotently creates the admin, demo, and classifier-eval users from
    .env. The eval user (phase 04 Part B, docs/DECISIONS.md D-29) is
    is_synthetic=True: it exists only to build the classifier eval set, not
    as a demo account, so it stays out of "real" dashboard aggregates -- its
    own profile/episodes are otherwise untouched here, only created."""
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
        _create_user_if_missing(
            db,
            settings.seed_eval_user_email,
            settings.seed_eval_user_password.get_secret_value(),
            is_admin=False,
            is_synthetic=True,
        )


@cli.command("profile")
def profile_cmd(
    user: str = typer.Option(..., "--user", help="Email of the user this profile is for"),
    answers: Path = typer.Option(
        ..., "--answers", help="Path to a JSON file of {question_key: answer_text}"
    ),
    save: bool = typer.Option(False, "--save", help="Write the extracted profile to preferences"),
) -> None:
    """Extracts a structured InterestProfile from guided-interview answers."""
    settings = get_settings()
    answers_data = json.loads(answers.read_text())
    llm = get_llm(settings)
    logger.info("extracting profile for %s from %s", user, answers)
    result, usage = extract_profile(answers_data, llm, settings)

    typer.echo(result.model_dump_json(indent=2))
    typer.echo(
        f"cost: ${usage.cost_usd:.4f} ({usage.units_in} in / {usage.units_out} out tokens, "
        f"{usage.latency_ms}ms)"
    )

    if save:
        with session_scope() as db:
            owner = db.scalar(select(User).where(User.email == user))
            if owner is None:
                typer.echo(f"no user with email {user!r}; run seed-users first", err=True)
                raise typer.Exit(code=1)
            prefs = db.get(Preferences, owner.id)
            if prefs is None:
                typer.echo(f"user {user!r} has no preferences row; run seed-users first", err=True)
                raise typer.Exit(code=1)
            prefs.interest_profile = result.model_dump()
            logger.info("saved profile for %s", user)
            typer.echo(f"saved profile for {user}")


def _create_episode(db, user: str, focus: str | None, minutes: int | None) -> int:
    """Shared by `new-episode` and `generate`: resolves the window start from
    the user's last ready episode (or 7 days back for a first episode) and the
    target length from the override or the user's saved preference."""
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
    logger.info(
        "created episode %s for %s (window_start=%s, target_minutes=%s)",
        episode.id,
        user,
        window_start.date(),
        target_minutes,
    )
    return episode.id


@cli.command("new-episode")
def new_episode(
    user: str = typer.Option(..., "--user", help="Email of the user to generate for"),
    focus: str | None = typer.Option(None, "--focus", help="Optional focus request"),
    minutes: int | None = typer.Option(None, "--minutes", help="Target length override"),
) -> None:
    with session_scope() as db:
        episode_id = _create_episode(db, user, focus, minutes)
        typer.echo(f"created episode {episode_id} for {user}")


@cli.command("plan")
def plan_cmd(episode_id: int = typer.Argument(..., help="Episode id to plan queries for")) -> None:
    episode = run_episode(episode_id, stop_after="planning")
    if episode.status == EpisodeStatus.FAILED:
        typer.echo(
            f"episode {episode_id} failed at {episode.failed_stage}: {episode.error}", err=True
        )
        raise typer.Exit(code=1)
    queries = episode.planned_queries or []
    typer.echo(f"episode {episode_id} planned {len(queries)} queries:")
    for q in queries:
        flag = " [focus]" if q.get("is_focus") else ""
        typer.echo(f"  [{q['topic']}] {q['query']}{flag}")


@cli.command("fetch")
def fetch_cmd(
    episode_id: int = typer.Argument(..., help="Episode id to fetch candidates for"),
) -> None:
    episode = run_episode(episode_id, stop_after="fetching")
    if episode.status == EpisodeStatus.FAILED:
        typer.echo(
            f"episode {episode_id} failed at {episode.failed_stage}: {episode.error}", err=True
        )
        raise typer.Exit(code=1)
    with session_scope() as db:
        count = db.scalar(
            select(func.count(func.distinct(ArticleScore.article_id))).where(
                ArticleScore.episode_id == episode_id
            )
        )
    typer.echo(f"episode {episode_id} fetched {count} unique candidate articles")
    typer.echo(f"run `candidates {episode_id}` to see them")


@cli.command("candidates")
def candidates_cmd(
    episode_id: int = typer.Argument(..., help="Episode id to list candidates for"),
) -> None:
    with session_scope() as db:
        rows = db.execute(
            select(ArticleScore.topic, Article.outlet, Article.published_at, Article.title)
            .join(Article, Article.id == ArticleScore.article_id)
            .where(ArticleScore.episode_id == episode_id)
            .order_by(ArticleScore.topic, Article.published_at.desc().nullslast())
        ).all()
    if not rows:
        typer.echo(f"no candidates for episode {episode_id}; run `fetch {episode_id}` first")
        raise typer.Exit(code=1)
    typer.echo(f"{'topic':<20} {'outlet':<24} {'date':<12} title")
    for topic, outlet, published_at, title in rows:
        date_str = published_at.date().isoformat() if published_at else "?"
        typer.echo(f"{(topic or ''):<20} {(outlet or ''):<24} {date_str:<12} {title or ''}")


@cli.command("generate")
def generate_cmd(
    user: str = typer.Option(..., "--user", help="Email of the user to generate for"),
    focus: str | None = typer.Option(None, "--focus", help="Optional focus request"),
    minutes: int | None = typer.Option(None, "--minutes", help="Target length override"),
    tts: str | None = typer.Option(None, "--tts", help="Override TTS provider, e.g. 'fake'"),
    stop_after: str | None = typer.Option(None, "--stop-after", help="Stage name to stop after"),
) -> None:
    """Creates an episode and runs the whole pipeline (plan -> ... -> assemble)."""
    with session_scope() as db:
        episode_id = _create_episode(db, user, focus, minutes)

    episode = run_episode(episode_id, stop_after=stop_after, tts_override=tts)
    if episode.status == EpisodeStatus.FAILED:
        typer.echo(
            f"episode {episode_id} failed at {episode.failed_stage}: {episode.error}", err=True
        )
        raise typer.Exit(code=1)

    typer.echo(f"episode {episode_id} status: {episode.status.value}")
    if episode.status == EpisodeStatus.READY:
        typer.echo(f"title: {episode.title}")
        typer.echo(f"audio: {episode.audio_path}")
        typer.echo(f"duration: {episode.duration_s:.1f}s")


@cli.command("transcript")
def transcript_cmd(episode_id: int = typer.Argument(..., help="Episode id to print")) -> None:
    with session_scope() as db:
        episode = db.get(Episode, episode_id)
        if episode is None or not episode.script:
            typer.echo(f"no script for episode {episode_id}", err=True)
            raise typer.Exit(code=1)
        prefs = db.get(Preferences, episode.user_id)
        names = {
            "host_a": (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex",
            "host_b": (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam",
        }
        script = Script.model_validate(episode.script)

    typer.echo(f"{script.title}\n{script.summary}\n")
    for section in script.sections:
        for turn in section.turns:
            typer.echo(f"{names[turn.speaker]}: {strip_audio_tags(turn.text)}")


def _print_grounding_flags(label: str, flags: list[dict]) -> None:
    typer.echo(f"  {label}: {len(flags)} unsupported claim(s)")
    for c in flags:
        typer.echo(f"    - section {c['section_index']} turn {c['turn_index']}: {c['claim']!r}")
        typer.echo(f"      reason: {c['reason']}")
        typer.echo(f"      suggested fix: {c['suggested_fix']}")


@cli.command("grounding")
def grounding_cmd(
    episode_id: int = typer.Argument(..., help="Episode id to show the grounding report for"),
) -> None:
    """Prints the grounding-check report stored on an episode (written by the
    scripting stage, phase 04 Part A) -- flags before and after the one
    allowed revision pass."""
    with session_scope() as db:
        episode = db.get(Episode, episode_id)
        if episode is None:
            typer.echo(f"no episode with id {episode_id}", err=True)
            raise typer.Exit(code=1)
        if episode.grounding_flags_initial is None:
            typer.echo(
                f"episode {episode_id} has no grounding report yet (scripting hasn't run)", err=True
            )
            raise typer.Exit(code=1)
        initial = episode.grounding_flags_initial
        final = episode.grounding_flags_final or []

    typer.echo(f"episode {episode_id} grounding report:")
    _print_grounding_flags("initial", initial)
    _print_grounding_flags("final", final)


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
