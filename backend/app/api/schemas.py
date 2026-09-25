"""Request/response models for the REST API (docs/phases/05-api-scheduler.md).
Kept separate from app/schemas.py, which is the pipeline's own internal value
types (Script, Usage, ...) -- these are the HTTP contract, not pipeline data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import InterestProfile


class LoginRequest(BaseModel):
    # Plain str, not pydantic's EmailStr: EmailStr needs the optional
    # email-validator dependency for a check login() already does for real
    # (a lookup against seeded users, which rejects any non-matching email).
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class MeResponse(BaseModel):
    id: int
    email: str
    is_admin: bool


class ProfileExtractRequest(BaseModel):
    answers: dict[str, str]


class QuestionOut(BaseModel):
    key: str
    question: str


class HostOut(BaseModel):
    name: str
    voice_id: str


class PreferencesOut(BaseModel):
    interest_profile: InterestProfile
    target_minutes: int
    tone: str | None
    host_a: HostOut
    host_b: HostOut
    schedule_cron: str | None
    timezone: str


class HostIn(BaseModel):
    name: str
    voice_id: str


class PreferencesUpdate(BaseModel):
    """All fields optional: PUT /preferences is a partial update, since the
    settings page saves whichever section the user just edited."""

    interest_profile: InterestProfile | None = None
    target_minutes: int | None = Field(default=None, ge=3, le=12)
    tone: str | None = None
    host_a: HostIn | None = None
    host_b: HostIn | None = None
    schedule_cron: str | None = None
    timezone: str | None = None


class VoiceOut(BaseModel):
    id: str
    name: str
    label: str
    preview_url: str | None = None


class EpisodeGenerateRequest(BaseModel):
    focus_request: str | None = None
    target_minutes: int | None = Field(default=None, ge=3, le=12)


class EpisodeCreated(BaseModel):
    id: int
    status: str
    target_minutes: int


class EpisodeListItem(BaseModel):
    id: int
    status: str
    title: str | None
    target_minutes: int
    duration_s: float | None
    created_at: datetime


class TranscriptTurn(BaseModel):
    speaker: str
    text: str


class SourceArticle(BaseModel):
    title: str | None
    outlet: str | None
    url: str


class StorySource(BaseModel):
    story_id: str
    articles: list[SourceArticle]


class StepSummary(BaseModel):
    stage: str
    status: str
    provider: str
    model: str | None
    units_in: int | None
    units_out: int | None
    cost_usd: float
    cost_is_estimate: bool
    latency_ms: int | None


class EpisodeDetail(BaseModel):
    id: int
    status: str
    failed_stage: str | None
    error: str | None
    title: str | None
    summary: str | None
    target_minutes: int
    duration_s: float | None
    created_at: datetime
    ready_at: datetime | None
    transcript: list[TranscriptTurn]
    sources: list[StorySource]
    steps: list[StepSummary]


class EventCreate(BaseModel):
    type: str
    episode_id: int | None = None
    payload: dict = Field(default_factory=dict)
