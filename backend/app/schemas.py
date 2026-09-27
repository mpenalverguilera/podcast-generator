from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Topic(BaseModel):
    name: str
    description: str
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    depth: Literal["headlines", "deep"] = "headlines"


class InterestProfile(BaseModel):
    topics: list[Topic] = Field(default_factory=list, max_length=8)
    avoid: list[str] = Field(default_factory=list)


class PlannedQuery(BaseModel):
    query: str
    topic: str
    is_focus: bool = False


class QueryPlan(BaseModel):
    queries: list[PlannedQuery] = Field(default_factory=list, max_length=30)


class RawArticle(BaseModel):
    url: str
    title: str | None = None
    outlet: str | None = None
    published_at: datetime | None = None
    highlights: list[str] = Field(default_factory=list)


class ContentResult(BaseModel):
    url: str
    text: str | None = None
    status: Literal["success", "error"] = "success"


class ArticleScoreResult(BaseModel):
    """Classifier output for one article. Distinct from the `article_scores`
    ORM row in app.models -- this is the value the Classifier protocol returns,
    the ORM model is what the pipeline persists from it."""

    topic: str
    relevance: float
    newsworthy: float
    already_covered: bool = False
    same_event_as_url: str | None = None
    score: float


class Turn(BaseModel):
    speaker: Literal["host_a", "host_b"]
    text: str


class Section(BaseModel):
    kind: Literal["intro", "story", "outro"]
    story_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    turns: list[Turn]


class OutlineSection(BaseModel):
    """One planned story section (scripting v2, docs/DECISIONS.md D-59; D-62
    renamed why_listener_cares -> stakes and target_words -> max_words -- the
    latter is a ceiling the writer may undershoot, not a target to hit). The
    outline call writes these; code then overwrites story_id to match the
    episode_items rows, so the model's own story_id only needs to be unique."""

    story_id: str
    source_ids: list[str]
    topic_label: str
    headline: str
    angle: str
    stakes: str
    depth: Literal["headlines", "deep"]
    max_words: int
    key_facts: list[str]
    must_not_cover: list[str]
    bridge_in: str | None = None


class DroppedSource(BaseModel):
    source_id: str
    reason: str


class Outline(BaseModel):
    cold_open_hook: str
    sections: list[OutlineSection]
    dropped: list[DroppedSource] = Field(default_factory=list)


class SectionDraft(BaseModel):
    """Model output for the section_writer and section_patch calls: only the
    turns. kind/story_id/source_ids come from the outline, set by code."""

    turns: list[Turn]


class FrameOutput(BaseModel):
    """Model output for the frame call (D-62, replacing the old `polish` step
    and its `PolishedScript`). The frame writes only the intro's cold open and
    preview and the outro -- never the story sections, which pass through
    untouched -- and never the AI-generated-briefing disclosure line, which
    code inserts between cold_open_turns and preview_turns as a fixed
    constant (`_DISCLOSURE_TURN` in script.py) so it can never be miswritten
    or mistaken for an unsupported claim by the grounder."""

    title: str
    summary: str
    cold_open_turns: list[Turn]
    preview_turns: list[Turn]
    outro_turns: list[Turn]


class ScriptStep(BaseModel):
    """One sub-call inside the scripting stage (outline, a section write, a
    grounding check, a patch, polish...), kept on the Script so the review
    export can show cost and latency per sub-step without extra DB rows.
    `section` is the index in the final script (intro 0, story k is k)."""

    step: str
    section: int | None = None
    words: int | None = None
    flags: int | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    note: str | None = None


class Script(BaseModel):
    title: str
    summary: str
    sections: list[Section]
    # None/empty for v1 episodes already in the DB, which must still load.
    outline: Outline | None = None
    trace: list[ScriptStep] = Field(default_factory=list)


class UnsupportedClaim(BaseModel):
    """One flagged claim from the grounding check (ARCHITECTURE §5.5 /
    docs/phases/04-quality.md Part A). Indices are into the *checked* Script's
    own `sections`/`turns` lists, so a claim can be located directly."""

    section_index: int
    turn_index: int
    claim: str
    reason: str
    suggested_fix: str


class GroundingReport(BaseModel):
    unsupported: list[UnsupportedClaim] = Field(default_factory=list, max_length=30)


class Usage(BaseModel):
    provider: str
    model: str | None = None
    units_in: int = 0
    units_out: int = 0
    cost_usd: float = 0.0
    cost_is_estimate: bool = False
    latency_ms: int = 0
    request_id: str | None = None
    usage_source: Literal["exact", "header", "estimated", "fake"] | None = None
    # D-44: 1 on a single classifier call that fell back from Jev to the OpenAI classifier
    # (FallbackClassifier), 0 otherwise; rank.run sums this into the ranking stage's aggregate
    # Usage the same way it already sums units_in/units_out/cost_usd, so
    # pipeline_steps.fallback_count is a real count.
    fallback_count: int = 0


class RenderedPrompt(BaseModel):
    name: str
    version: int
    text: str
