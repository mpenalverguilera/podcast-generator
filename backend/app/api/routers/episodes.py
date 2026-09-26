import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    EpisodeCreated,
    EpisodeDetail,
    EpisodeGenerateRequest,
    EpisodeListItem,
    SourceArticle,
    StepSummary,
    TranscriptSection,
    TranscriptTurn,
)
from app.auth import create_media_token, current_user, require_owner_or_admin, verify_media_token
from app.db import get_db
from app.models import (
    Article,
    ArticleScore,
    Episode,
    EpisodeStatus,
    EpisodeTrigger,
    Event,
    PipelineStep,
    User,
)
from app.pipeline.episodes import (
    EpisodeConflict,
    create_episode,
    mark_resuming,
    run_in_background,
)
from app.pipeline.script import strip_audio_tags
from app.schemas import Script

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("/generate", response_model=EpisodeCreated, status_code=status.HTTP_201_CREATED)
def generate_episode(
    body: EpisodeGenerateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EpisodeCreated:
    try:
        episode = create_episode(
            db,
            user,
            focus=body.focus_request,
            target_minutes=body.target_minutes,
            trigger=EpisodeTrigger.MANUAL,
        )
    except EpisodeConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.add(
        Event(
            user_id=user.id,
            episode_id=episode.id,
            type="generate_clicked",
            payload={
                "target_minutes": episode.target_minutes,
                "overridden": body.target_minutes is not None,
            },
            is_synthetic=user.is_synthetic,
        )
    )
    db.commit()
    episode_id = episode.id

    run_in_background(episode_id)
    return EpisodeCreated(
        id=episode_id, status=EpisodeStatus.PENDING.value, target_minutes=episode.target_minutes
    )


@router.get("", response_model=list[EpisodeListItem])
def list_episodes(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[EpisodeListItem]:
    rows = db.scalars(
        select(Episode).where(Episode.user_id == user.id).order_by(Episode.created_at.desc())
    ).all()
    return [
        EpisodeListItem(
            id=e.id,
            status=e.status.value,
            failed_stage=e.failed_stage,
            error=e.error,
            trigger=e.trigger.value,
            focus_request=e.focus_request,
            title=e.title,
            target_minutes=e.target_minutes,
            duration_s=e.duration_s,
            created_at=e.created_at,
        )
        for e in rows
    ]


def _article_id(source_id: str) -> int | None:
    """Script source ids are "a<article id>" (the id the script writer saw)."""
    return int(source_id[1:]) if source_id[1:].isdigit() else None


def _build_sections(episode: Episode, db: Session) -> list[TranscriptSection]:
    """The script grouped the way the episode page shows it: each story with
    its heading, topic, turns and the sources right under it."""
    if not episode.script:
        return []
    script = Script.model_validate(episode.script)
    prefs = episode.user.preferences
    names = {
        "host_a": (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex",
        "host_b": (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam",
    }

    article_ids = {
        aid
        for section in script.sections
        if section.kind == "story"
        for sid in section.source_ids
        if (aid := _article_id(sid)) is not None
    }
    articles: dict[int, Article] = {}
    topics: dict[int, str] = {}
    if article_ids:
        articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(article_ids)))}
        # An article can be scored against several topics; keep its best one.
        scores = db.scalars(
            select(ArticleScore)
            .where(ArticleScore.episode_id == episode.id, ArticleScore.article_id.in_(article_ids))
            .order_by(ArticleScore.score.desc().nulls_last())
        )
        for score in scores:
            if score.topic:
                topics.setdefault(score.article_id, score.topic)

    sections = []
    for section in script.sections:
        sources = []
        if section.kind == "story":
            sources = [
                articles[aid]
                for sid in section.source_ids
                if (aid := _article_id(sid)) is not None and aid in articles
            ]
        lead = sources[0] if sources else None
        sections.append(
            TranscriptSection(
                kind=section.kind,
                story_id=section.story_id,
                heading=lead.title if lead else None,
                topic=topics.get(lead.id) if lead else None,
                turns=[
                    TranscriptTurn(speaker=names[t.speaker], text=strip_audio_tags(t.text))
                    for t in section.turns
                ],
                sources=[SourceArticle(title=a.title, outlet=a.outlet, url=a.url) for a in sources],
            )
        )
    return sections


def _my_rating(episode: Episode, user: User, db: Session) -> int | None:
    """Latest episode_rated event wins; events stay append-only, and a 0
    (the user un-clicking their thumb) reads as no rating."""
    latest = db.scalar(
        select(Event)
        .where(
            Event.episode_id == episode.id,
            Event.user_id == user.id,
            Event.type == "episode_rated",
        )
        .order_by(Event.id.desc())
        .limit(1)
    )
    value = (latest.payload or {}).get("value") if latest else None
    return value if value in (1, -1) else None


def _build_steps(episode: Episode, db: Session) -> list[StepSummary]:
    steps = db.scalars(
        select(PipelineStep).where(PipelineStep.episode_id == episode.id).order_by(PipelineStep.id)
    ).all()
    return [
        StepSummary(
            stage=s.stage,
            status=s.status.value,
            provider=s.provider,
            model=s.model,
            units_in=s.units_in,
            units_out=s.units_out,
            cost_usd=float(s.cost_usd or 0),
            cost_is_estimate=s.cost_is_estimate,
            latency_ms=s.latency_ms,
        )
        for s in steps
    ]


@router.get("/{episode_id}", response_model=EpisodeDetail)
def get_episode(
    episode_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> EpisodeDetail:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "episode not found")
    require_owner_or_admin(episode, user)

    return EpisodeDetail(
        id=episode.id,
        status=episode.status.value,
        failed_stage=episode.failed_stage,
        error=episode.error,
        trigger=episode.trigger.value,
        focus_request=episode.focus_request,
        title=episode.title,
        summary=episode.summary,
        target_minutes=episode.target_minutes,
        duration_s=episode.duration_s,
        created_at=episode.created_at,
        ready_at=episode.ready_at,
        audio_url=(
            f"/episodes/{episode.id}/audio?t={create_media_token('episode', episode.id)}"
            if episode.audio_path
            else None
        ),
        my_rating=_my_rating(episode, user, db),
        sections=_build_sections(episode, db),
        steps=_build_steps(episode, db),
    )


@router.post("/{episode_id}/retry", response_model=EpisodeCreated)
def retry_episode(
    episode_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> EpisodeCreated:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "episode not found")
    require_owner_or_admin(episode, user)

    # The status flips out of "failed" in the DB before the thread starts, so
    # a second click (or a concurrent generate) gets a 409 instead of
    # starting a second runner on the same episode.
    try:
        resume_at = mark_resuming(db, episode.id)
    except EpisodeConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()

    logger.info("retrying episode %s from %s", episode.id, resume_at.value)
    run_in_background(episode.id)
    return EpisodeCreated(
        id=episode.id, status=resume_at.value, target_minutes=episode.target_minutes
    )


@router.get("/{episode_id}/audio")
def get_episode_audio(
    episode_id: int,
    t: str = Query(description="media token from the episode detail's audio_url"),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Authenticated by the scoped media token in `audio_url`, not the Bearer
    header: a native <audio src> can't send headers. Only the owner or an
    admin ever receives that token (GET /episodes/{id}), so the ownership
    check happened there. docs/DECISIONS.md D-40."""
    verify_media_token(t, "episode", episode_id)
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "episode not found")
    if not episode.audio_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no audio for this episode yet")

    # Starlette's FileResponse handles Range requests (206 partial content)
    # natively -- confirmed by reading starlette.responses.FileResponse's
    # source (docs/ARCHITECTURE.md §7's own [VERIFY] item), so no custom
    # ranged-response implementation is needed.
    return FileResponse(episode.audio_path, media_type="audio/mpeg")
