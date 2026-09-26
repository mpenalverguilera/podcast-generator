import logging
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.adapters.llm import get_llm
from app.api.schemas import (
    HostOut,
    LengthOption,
    PreferencesOut,
    PreferencesUpdate,
    ProfileExtractRequest,
    QuestionOut,
    VoiceOut,
)
from app.auth import create_media_token, current_user, verify_media_token
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Event, User
from app.pipeline.profile import GUIDED_QUESTIONS, extract_profile
from app.pipeline.rank import story_count_for
from app.scheduler import sync_user_schedule
from app.schemas import InterestProfile
from app.voices import CURATED_VOICES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["preferences"])


@router.get("/profile/questions", response_model=list[QuestionOut])
def profile_questions() -> list[QuestionOut]:
    return [QuestionOut(**q) for q in GUIDED_QUESTIONS]


@router.post("/profile/extract", response_model=InterestProfile)
def profile_extract(
    body: ProfileExtractRequest,
    _user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> InterestProfile:
    """Proposes a profile without saving it -- the guided-interview UI lets
    the user review/edit it as tags before PUT /preferences persists it."""
    llm = get_llm(settings)
    profile, _usage = extract_profile(body.answers, llm, settings)
    return profile


def _next_run_at(schedule_cron: str | None, timezone: str) -> datetime | None:
    """Computed from the saved cron rather than asked of the live scheduler,
    so it reads the same whether or not the scheduler is running."""
    if not schedule_cron:
        return None
    trigger = CronTrigger.from_crontab(schedule_cron, timezone=timezone)
    return trigger.get_next_fire_time(None, datetime.now(UTC))


def _preferences_out(user: User) -> PreferencesOut:
    prefs = user.preferences
    return PreferencesOut(
        interest_profile=InterestProfile.model_validate(prefs.interest_profile or {}),
        target_minutes=prefs.target_minutes,
        tone=prefs.tone,
        host_a=HostOut(**{"name": "Alex", "voice_id": "", **(prefs.host_a or {})}),
        host_b=HostOut(**{"name": "Sam", "voice_id": "", **(prefs.host_b or {})}),
        schedule_cron=prefs.schedule_cron,
        timezone=prefs.timezone,
        next_run_at=_next_run_at(prefs.schedule_cron, prefs.timezone),
    )


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(current_user)) -> PreferencesOut:
    if user.preferences is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preferences for this user")
    return _preferences_out(user)


@router.get("/preferences/length-options", response_model=list[LengthOption])
def length_options() -> list[LengthOption]:
    """How many stories each episode length gets, for the settings slider's
    "~6 min · ~5 stories" estimate -- served from the ranker's own rule so
    the frontend doesn't keep a copy that can drift."""
    return [LengthOption(minutes=m, stories=story_count_for(m)) for m in range(3, 13)]


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(
    body: PreferencesUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PreferencesOut:
    prefs = user.preferences
    if prefs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preferences for this user")

    fields = body.model_dump(exclude_unset=True)

    # Validate the cron/timezone combination before touching the DB -- an
    # invalid one would otherwise only surface later, as an unhandled error
    # from sync_user_schedule after the bad value was already persisted.
    resolved_cron = fields.get("schedule_cron", prefs.schedule_cron)
    resolved_tz = fields.get("timezone", prefs.timezone)
    if resolved_cron:
        try:
            CronTrigger.from_crontab(resolved_cron, timezone=resolved_tz)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid schedule_cron/timezone: {exc}"
            ) from exc

    if "interest_profile" in fields:
        prefs.interest_profile = fields["interest_profile"]
        db.add(Event(user_id=user.id, type="profile_updated", is_synthetic=user.is_synthetic))

    settings_fields = {k: v for k, v in fields.items() if k != "interest_profile"}
    if settings_fields:
        for key, value in settings_fields.items():
            setattr(prefs, key, value)
        db.add(Event(user_id=user.id, type="settings_changed", is_synthetic=user.is_synthetic))

    db.commit()
    db.refresh(prefs)

    # Re-sync this user's scheduler job regardless of which fields changed --
    # sync_user_schedule is a cheap idempotent no-op if the cron didn't change.
    sync_user_schedule(user.id, prefs.schedule_cron, prefs.timezone)

    return _preferences_out(user)


def _voice_preview_url(settings: Settings, voice_id: str) -> str | None:
    # Tokenised like episode audio (D-40): <audio src> can't send the Bearer
    # header, and previews stay private rather than an open download.
    preview_path = Path(settings.data_dir) / "voice_previews" / f"{voice_id}.mp3"
    if not preview_path.exists():
        return None
    return f"/voices/{voice_id}/preview?t={create_media_token('voice', voice_id)}"


@router.get("/voices", response_model=list[VoiceOut])
def list_voices(
    _user: User = Depends(current_user), settings: Settings = Depends(get_settings)
) -> list[VoiceOut]:
    return [
        VoiceOut(
            id=v.id, name=v.name, label=v.label, preview_url=_voice_preview_url(settings, v.id)
        )
        for v in CURATED_VOICES
    ]


@router.get("/voices/{voice_id}/preview")
def voice_preview(
    voice_id: str,
    t: str = Query(description="media token from GET /voices' preview_url"),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    verify_media_token(t, "voice", voice_id)
    preview_path = Path(settings.data_dir) / "voice_previews" / f"{voice_id}.mp3"
    if not preview_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview for this voice")
    return FileResponse(preview_path, media_type="audio/mpeg")
