"""Request/response models for the REST API (docs/phases/05-api-scheduler.md).
Kept separate from app/schemas.py, which is the pipeline's own internal value
types (Script, Usage, ...) -- these are the HTTP contract, not pipeline data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas import InterestProfile
from app.voices import CURATED_VOICES

CURATED_VOICE_IDS = {v.id for v in CURATED_VOICES}


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
    # False until the user saves at least one topic -- the frontend sends
    # first-time users to the settings page on this.
    has_profile: bool


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
    # Computed from schedule_cron/timezone, not read from the live scheduler.
    next_run_at: datetime | None


class LengthOption(BaseModel):
    minutes: int
    stories: int


class HostIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    voice_id: str

    @field_validator("voice_id")
    @classmethod
    def _curated_voice(cls, voice_id: str) -> str:
        # Rejected here, not at the voicing stage -- by then planning,
        # fetching, ranking and scripting would already have been paid for.
        if voice_id not in CURATED_VOICE_IDS:
            raise ValueError("voice_id must be one of GET /voices")
        return voice_id


class PreferencesUpdate(BaseModel):
    """All fields optional: PUT /preferences is a partial update, since the
    settings page saves whichever section the user just edited."""

    interest_profile: InterestProfile | None = None
    target_minutes: int | None = Field(default=None, ge=3, le=12)
    # The settings page's three options; free text here would be pasted
    # straight into the script-writer prompt.
    tone: Literal["conversational", "focused", "playful"] | None = None
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
    failed_stage: str | None
    error: str | None
    trigger: str
    focus_request: str | None
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


class TranscriptSection(BaseModel):
    """One script section as the episode page shows it: a story's heading
    (its first source's title) and topic, its turns, and its sources right
    under it. Intro and outro have no heading, topic or sources."""

    kind: Literal["intro", "story", "outro"]
    story_id: str | None
    heading: str | None
    topic: str | None
    turns: list[TranscriptTurn]
    sources: list[SourceArticle]


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
    trigger: str
    focus_request: str | None
    title: str | None
    summary: str | None
    target_minutes: int
    duration_s: float | None
    created_at: datetime
    ready_at: datetime | None
    # Includes a short-lived media token (?t=...), since <audio src> can't
    # send the Authorization header. None until the episode has audio.
    audio_url: str | None
    # The caller's latest episode_rated value; a 0 ("cleared") reads as None.
    my_rating: Literal[1, -1] | None
    sections: list[TranscriptSection]
    steps: list[StepSummary]


class EventCreate(BaseModel):
    """Only the player/rating events a client may send. The server emits
    generate_clicked, profile_updated and settings_changed itself, so a
    client can't forge those into the phase-07 metrics. Every client event
    is about one episode. Payload shapes: play_progress needs
    {"position_s": number >= 0}; episode_rated needs {"value": 1 | -1 | 0},
    where 0 clears the rating."""

    type: Literal["play_started", "play_progress", "play_completed", "episode_rated"]
    episode_id: int
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_payload(self) -> "EventCreate":
        if self.type == "play_progress":
            position = self.payload.get("position_s")
            if not isinstance(position, int | float) or isinstance(position, bool) or position < 0:
                raise ValueError("play_progress needs payload.position_s >= 0")
        if self.type == "episode_rated":
            value = self.payload.get("value")
            if isinstance(value, bool) or value not in (1, -1, 0):
                raise ValueError("episode_rated needs payload.value of 1, -1 or 0 (clear)")
        return self
