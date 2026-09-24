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


class Script(BaseModel):
    title: str
    summary: str
    sections: list[Section]


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


class RenderedPrompt(BaseModel):
    name: str
    version: int
    text: str
