from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Episode
from app.schemas import RenderedPrompt, Usage


class _StubPlannedQueries(BaseModel):
    """Placeholder for the real QueryPlan schema (phase 02's query_planner
    prompt). Exists only to prove the LLM adapter -> Usage wiring works."""

    note: str = "stub"


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    prompt = RenderedPrompt(name="planner_stub", version=0, text="Plan queries (stub).")
    _, usage = adapters.llm.structured(
        prompt, _StubPlannedQueries, model="gpt-6-luna", reasoning="none"
    )
    return usage
