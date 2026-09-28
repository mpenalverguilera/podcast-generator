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
    # classifier.v2 (D-61): the title/highlights show the event happened before the episode
    # window, whatever `published_at` says. Not persisted: rank.py uses it in the same run.
    is_stale: bool = False


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
    # D-65 (outline.v3): `angle` above now carries the section's *take* -- one
    # declarative, arguable claim -- instead of a question. These two give the
    # hosts something real to discuss beyond it. Defaulted so outlines already
    # stored on episodes (voice.py, the transcript API) still validate.
    tension: str | None = None
    open_questions: list[str] = Field(default_factory=list)


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
    and its `PolishedScript`; D-63 dropped the AI-generated-briefing
    disclosure line this once inserted between cold_open_turns and
    preview_turns). The frame writes only the intro's cold open and preview
    and the outro -- never the story sections, which pass through
    untouched."""

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


AudioTag = Literal["[laughs]", "[chuckles]", "[curious]", "[surprised]", "[sighs]"]


class TagFix(BaseModel):
    """An audio tag the grounding check judged wrong for its line (D-68).
    Applied in code as a plain replace of `old_tag` by `new_tag` ("" removes
    it): the spoken words never change, so no patch or re-check is needed.
    Kept apart from `unsupported` so the fact-flag counts stay comparable."""

    section_index: int
    turn_index: int
    old_tag: str
    new_tag: str
    reason: str


class GroundingReport(BaseModel):
    unsupported: list[UnsupportedClaim] = Field(default_factory=list, max_length=30)
    tag_fixes: list[TagFix] = Field(default_factory=list)


class ClaimCheck(BaseModel):
    """One statement the grounding check looked at (grounding_check.v4, D-65).
    Field order is deliberate: the model writes what the source says
    (`evidence`) before it commits to a `verdict` -- cheap reasoning with no
    reasoning-effort cost, the D-61 follow-up for its flip-flopping. A "take"
    is a host's interpretation that adds no new specific: allowed."""

    section_index: int
    turn_index: int
    claim: str
    evidence: str
    verdict: Literal["supported", "take", "unsupported"]
    suggested_fix: str


class TagCheck(BaseModel):
    """One audio tag the grounding check looked at (grounding_check.v5,
    D-68). Reason-first like ClaimCheck: `reacts_to` is what in this turn or
    the previous one the tag's emotion answers to, written before the
    verdict. A tag is a claim about emotion, so it is grounded in the
    dialogue the way a fact is grounded in the sources."""

    section_index: int
    turn_index: int
    tag: str
    reacts_to: str
    verdict: Literal["fits", "swap", "remove"]
    proposed_tag: AudioTag | None


class GroundingChecks(BaseModel):
    """What the grounding model returns (D-65). grounding.check() keeps only
    the "unsupported" rows and hands back a GroundingReport, so everything
    downstream -- patching, persisted flags, the CLI -- is unchanged."""

    # No max_length: a long deep section can have many checkable statements, and
    # a validation error here would fail the whole stage. to_report() caps the
    # flags it keeps at GroundingReport's 30.
    checks: list[ClaimCheck] = Field(default_factory=list)
    tags: list[TagCheck] = Field(default_factory=list)


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
