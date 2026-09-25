import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    # SQLAlchemy's Enum type stores each member's .name (e.g. "PENDING") by
    # default, not .value ("pending"). ARCHITECTURE §5/§7 specify lowercase
    # values, so every native enum column must override this explicitly.
    return Enum(enum_cls, name=name, values_callable=lambda obj: [e.value for e in obj])


class EpisodeStatus(enum.StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    FETCHING = "fetching"
    RANKING = "ranking"
    EXTRACTING = "extracting"
    SCRIPTING = "scripting"
    VOICING = "voicing"
    ASSEMBLING = "assembling"
    READY = "ready"
    FAILED = "failed"


class EpisodeTrigger(enum.StrEnum):
    SCHEDULE = "schedule"
    MANUAL = "manual"


class ContentSource(enum.StrEnum):
    TEXT = "text"
    HIGHLIGHTS = "highlights"


class StepStatus(enum.StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    preferences: Mapped["Preferences"] = relationship(back_populates="user", uselist=False)
    episodes: Mapped[list["Episode"]] = relationship(back_populates="user")
    events: Mapped[list["Event"]] = relationship(back_populates="user")


class Preferences(Base):
    __tablename__ = "preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    interest_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    target_minutes: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    tone: Mapped[str | None] = mapped_column(String, nullable=True)
    host_a: Mapped[dict] = mapped_column(JSONB, default=dict)
    host_b: Mapped[dict] = mapped_column(JSONB, default=dict)
    schedule_cron: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str] = mapped_column(String, default="UTC", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="preferences")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    url_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    outlet: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    highlights: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_source: Mapped[ContentSource] = mapped_column(
        _pg_enum(ContentSource, "content_source"), default=ContentSource.HIGHLIGHTS, nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ArticleScore(Base):
    __tablename__ = "article_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    newsworthy: Mapped[float | None] = mapped_column(Float, nullable=True)
    already_covered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    same_event_as_url: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classifier: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[EpisodeStatus] = mapped_column(
        _pg_enum(EpisodeStatus, "episode_status"), default=EpisodeStatus.PENDING, nullable=False
    )
    failed_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[EpisodeTrigger] = mapped_column(
        _pg_enum(EpisodeTrigger, "episode_trigger"), nullable=False
    )
    focus_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_queries: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    script: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt_versions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tts_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grounding_flags_initial: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    grounding_flags_final: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="episodes")
    steps: Mapped[list["PipelineStep"]] = relationship(back_populates="episode")
    items: Mapped[list["EpisodeItem"]] = relationship(back_populates="episode")


class EpisodeItem(Base):
    __tablename__ = "episode_items"
    __table_args__ = (UniqueConstraint("episode_id", "article_id"),)

    # ARCHITECTURE §7 lists no explicit PK for this table; a surrogate id is the
    # simplest unambiguous choice.
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    story_id: Mapped[str] = mapped_column(String, nullable=False)

    episode: Mapped["Episode"] = relationship(back_populates="items")


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[StepStatus] = mapped_column(_pg_enum(StepStatus, "step_status"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    units_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    cost_is_estimate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Beyond the literal ARCHITECTURE §7 list: D-12 wants ElevenLabs' character-cost
    # header provenance and request-id stored somewhere, and there's no other place
    # for them to live.
    usage_source: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # D-39: how many candidates in this stage fell back from Jev to Luna (FallbackClassifier).
    # Meaningful only for the ranking stage once classifier_provider="jev"; 0 elsewhere.
    fallback_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    episode: Mapped["Episode"] = relationship(back_populates="steps")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"), nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="events")
