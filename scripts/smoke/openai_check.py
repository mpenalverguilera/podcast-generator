"""Phase 00 smoke test: OpenAI.

Confirms:
- which of gpt-6-sol / gpt-6-luna / gpt-6-astra the key can see
- the exact `client.responses.parse(..., text_format=...)` call shape and usage fields

Run: uv run python ../scripts/smoke/openai_check.py   (from backend/, where the venv lives)
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

CANDIDATE_MODELS = ["gpt-6-sol", "gpt-6-luna", "gpt-6-astra"]


class TinyPlan(BaseModel):
    topic: str = Field(description="one short topic name")
    queries: list[str] = Field(description="1-2 short search queries about the topic", max_length=2)


def main() -> int:
    client = OpenAI()

    print("== models available to this key ==")
    model_ids = {m.id for m in client.models.list()}
    for candidate in CANDIDATE_MODELS:
        print(f"{candidate}: {'FOUND' if candidate in model_ids else 'missing'}")

    planner_model = next((m for m in CANDIDATE_MODELS if m in model_ids), None)
    if planner_model is None:
        print("No candidate model found on this key; picking the first available model instead.")
        planner_model = sorted(model_ids)[0] if model_ids else None
    if planner_model is None:
        print("No models at all visible to this key.")
        return 1

    print(f"\n== structured output call on {planner_model} (reasoning=none) ==")
    resp = client.responses.parse(
        model=planner_model,
        input=[
            {"role": "system", "content": "You plan short web search queries for a news podcast."},
            {"role": "user", "content": "Topic: AI voice agents. Give 1-2 queries about this week's news."},
        ],
        text_format=TinyPlan,
        reasoning={"effort": "none"},
    )

    print("output_parsed:", resp.output_parsed)
    print("usage:", resp.usage)
    print("usage fields:", list(resp.usage.model_dump().keys()) if resp.usage else None)

    if resp.output_parsed is None:
        print("Model refused / output_parsed is None.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
