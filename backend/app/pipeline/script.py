from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Episode
from app.schemas import RenderedPrompt, Usage


class _StubScript(BaseModel):
    """Placeholder for the real Script schema (phase 03's script_writer
    prompt). Exists only to prove the LLM adapter -> Usage wiring works."""

    note: str = "stub"


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    prompt = RenderedPrompt(name="script_stub", version=0, text="Write the script (stub).")
    _, usage = adapters.llm.structured(prompt, _StubScript, model="gpt-6-sol", reasoning="medium")
    return usage
