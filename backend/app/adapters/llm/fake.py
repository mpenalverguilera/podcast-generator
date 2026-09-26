import re
import time

from pydantic import BaseModel

from app.schemas import RenderedPrompt, Usage

_SHORT_ID_RE = re.compile(r"\[(a\d+)\]")
_WORD_TARGET_RE = re.compile(r"about (\d+) words")
_FAKE_SENTENCE = "This is a fake sentence for testing scripts. "

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
    "ArticleScoreResult": {
        "topic": "general",
        "relevance": 0.8,
        "newsworthy": 0.8,
        "already_covered": False,
        "score": 0.64,
    },
    "GroundingReport": {"unsupported": []},
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


def _fake_script(prompt_text: str) -> dict:
    """Script can't be a static _REGISTRY fixture: its source_ids must be a
    subset of the short article ids (e.g. "a12") that script.py generated for
    *this* episode's real, DB-assigned article ids, which a canned fixture
    can't predict. Instead, pull the ids straight out of the rendered prompt's
    `[aNN]` article block and build a script around exactly those -- still
    fully deterministic for a given prompt.

    Length follows the prompt's own "about N words" target: intro (64 words)
    and outro (40) are fixed, and each story's three turns share the rest in
    8-word sentences, so the script lands inside the +-15% budget for any
    episode length and story count (docs/DECISIONS.md D-40).
    """
    ids = _SHORT_ID_RE.findall(prompt_text) or ["a0"]
    target = _WORD_TARGET_RE.search(prompt_text)
    per_story_words = (int(target.group(1)) - 104) / len(ids) if target else 168
    per_turn = max(1, round(per_story_words / 3 / 8))
    sections = [
        {
            "kind": "intro",
            "story_id": None,
            "source_ids": [],
            "turns": [
                {"speaker": "host_a", "text": _FAKE_SENTENCE * 4},
                {"speaker": "host_b", "text": _FAKE_SENTENCE * 4},
            ],
        }
    ]
    for i, sid in enumerate(ids):
        sections.append(
            {
                "kind": "story",
                "story_id": f"s{i + 1}",
                "source_ids": [sid],
                "turns": [
                    {"speaker": "host_a", "text": _FAKE_SENTENCE * per_turn},
                    {"speaker": "host_b", "text": _FAKE_SENTENCE * per_turn},
                    {"speaker": "host_a", "text": _FAKE_SENTENCE * per_turn},
                ],
            }
        )
    sections.append(
        {
            "kind": "outro",
            "story_id": None,
            "source_ids": [],
            "turns": [{"speaker": "host_b", "text": _FAKE_SENTENCE * 5}],
        }
    )
    return {"title": "Fake Episode", "summary": "A fake summary for testing.", "sections": sections}


class FakeLLM:
    """Deterministic LLM for tests/CLI iteration. Never fabricates data for a
    schema nobody's told it how to fake: falls back to zero-arg construction
    only if every field has a default, otherwise raises."""

    def structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], model: str, reasoning: str
    ) -> tuple[BaseModel, Usage]:
        start = time.monotonic()
        name = schema.__name__
        if name == "Script":
            parsed = schema.model_validate(_fake_script(prompt.text))
        elif name in _REGISTRY:
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
