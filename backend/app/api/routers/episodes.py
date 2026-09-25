import logging

from fastapi import APIRouter, Depends, HTTPException, status
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
    StorySource,
    TranscriptTurn,
)
from app.auth import current_user, require_owner_or_admin
from app.db import get_db
from app.models import Article, Episode, EpisodeStatus, EpisodeTrigger, Event, PipelineStep, User
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
            title=e.title,
            target_minutes=e.target_minutes,
            duration_s=e.duration_s,
            created_at=e.created_at,
        )
        for e in rows
    ]


def _build_transcript(episode: Episode) -> list[TranscriptTurn]:
    if not episode.script:
        return []
    prefs = episode.user.preferences
    names = {
        "host_a": (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex",
        "host_b": (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam",
    }
    script = Script.model_validate(episode.script)
    return [
        TranscriptTurn(speaker=names[turn.speaker], text=strip_audio_tags(turn.text))
        for section in script.sections
        for turn in section.turns
    ]


def _build_sources(episode: Episode, db: Session) -> list[StorySource]:
    if not episode.script:
        return []
    script = Script.model_validate(episode.script)
    story_sections = [s for s in script.sections if s.kind == "story" and s.story_id]

    article_ids = {
        int(sid[1:])
        for section in story_sections
        for sid in section.source_ids
        if sid[1:].isdigit()
    }
    if not article_ids:
        return []
    articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(article_ids)))}

    sources = []
    for section in story_sections:
        articles_out = [
            SourceArticle(title=a.title, outlet=a.outlet, url=a.url)
            for sid in section.source_ids
            if sid[1:].isdigit() and (a := articles.get(int(sid[1:]))) is not None
        ]
        if articles_out:
            sources.append(StorySource(story_id=section.story_id, articles=articles_out))
    return sources


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
        title=episode.title,
        summary=episode.summary,
        target_minutes=episode.target_minutes,
        duration_s=episode.duration_s,
        created_at=episode.created_at,
        ready_at=episode.ready_at,
        transcript=_build_transcript(episode),
        sources=_build_sources(episode, db),
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
    episode_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> FileResponse:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "episode not found")
    require_owner_or_admin(episode, user)
    if not episode.audio_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no audio for this episode yet")

    # Starlette's FileResponse handles Range requests (206 partial content)
    # natively -- confirmed by reading starlette.responses.FileResponse's
    # source (docs/ARCHITECTURE.md §7's own [VERIFY] item), so no custom
    # ranged-response implementation is needed.
    return FileResponse(episode.audio_path, media_type="audio/mpeg")
