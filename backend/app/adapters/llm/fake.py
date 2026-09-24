import time

from pydantic import BaseModel

from app.schemas import RenderedPrompt, Usage

# Canned payloads keyed by schema class name, for schemas whose all-default
# construction wouldn't produce a useful fixture. Phases 02-04 add entries here
# as their prompts and schemas land.
_REGISTRY: dict[str, dict] = {
    # Matches the CLAUDE.md phase 02 acceptance example (health tech + AI voice
    # agents for work, Formula 1 for fun, celebrity gossip avoided).
    "InterestProfile": {
        "topics": [
            {
                "name": "AI voice agents",
                "description": (
                    "Voice AI products, models, funding and adoption in health tech and beyond"
                ),
                "include": ["voice agent", "speech AI", "health tech AI"],
                "exclude": ["smart speakers"],
                "depth": "deep",
            },
            {
                "name": "Formula 1",
                "description": "Formula 1 races, standings and team news",
                "include": ["F1", "grand prix"],
                "exclude": [],
                "depth": "headlines",
            },
        ],
        "avoid": ["celebrity gossip"],
    },
    "QueryPlan": {
        "queries": [
            {
                "topic": "AI voice agents",
                "query": "latest news on AI voice agent startups this week",
                "is_focus": False,
            },
            {
                "topic": "AI voice agents",
                "query": "AI voice agent funding rounds this month",
                "is_focus": False,
            },
            {
                "topic": "Formula 1",
                "query": "Formula 1 race results this week",
                "is_focus": False,
            },
            {
                "topic": "focus",
                "query": "latest on prior authorization rules for health insurance",
                "is_focus": True,
            },
        ]
    },
}


class FakeLLM:
    """Deterministic LLM for tests/CLI iteration. Never fabricates data for a
    schema nobody's told it how to fake: falls back to zero-arg construction
    only if every field has a default, otherwise raises."""

    def structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], model: str, reasoning: str
    ) -> tuple[BaseModel, Usage]:
        start = time.monotonic()
        name = schema.__name__
        if name in _REGISTRY:
            parsed = schema.model_validate(_REGISTRY[name])
        else:
            try:
                parsed = schema()
            except Exception as exc:
                raise NotImplementedError(
                    f"FakeLLM has no fixture for {name}; add one to _REGISTRY"
                ) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = Usage(provider="fake", model=model, latency_ms=latency_ms, usage_source="fake")
        return parsed, usage
