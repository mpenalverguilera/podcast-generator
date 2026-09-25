import logging
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.adapters.llm import get_llm
from app.api.schemas import (
    HostOut,
    PreferencesOut,
    PreferencesUpdate,
    ProfileExtractRequest,
    QuestionOut,
    VoiceOut,
)
from app.auth import current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Event, User
from app.pipeline.profile import GUIDED_QUESTIONS, extract_profile
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
    )


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(current_user)) -> PreferencesOut:
    if user.preferences is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preferences for this user")
    return _preferences_out(user)


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
    preview_path = Path(settings.data_dir) / "voice_previews" / f"{voice_id}.mp3"
    return f"/voices/{voice_id}/preview" if preview_path.exists() else None


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
    _user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    preview_path = Path(settings.data_dir) / "voice_previews" / f"{voice_id}.mp3"
    if not preview_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview for this voice")
    return FileResponse(preview_path, media_type="audio/mpeg")
