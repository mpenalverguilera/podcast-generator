import math
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
    "GroundingChecks": {"checks": []},
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


def _ids_in(prompt_text: str) -> list[str]:
    """The `[aNN]` short article ids in a rendered prompt, first-seen order,
    no repeats. They can't be a static fixture: they come from this
    episode's DB-assigned article ids."""
    return list(dict.fromkeys(_SHORT_ID_RE.findall(prompt_text))) or ["a0"]


def _fake_outline(prompt_text: str) -> dict:
    """One section per `[aNN]` id in the outline prompt, story_ids s1.., each
    asking for 100 words (script.py scales these to the story budget)."""
    sections = [
        {
            "story_id": f"s{i + 1}",
            "source_ids": [sid],
            "topic_label": "fake topic",
            "headline": f"Fake headline {i + 1}",
            "angle": "a fake angle",
            "stakes": "a fake stake",
            "depth": "headlines",
            "max_words": 100,
            "key_facts": [f"fake fact {i + 1}"],
            "must_not_cover": [],
            "bridge_in": None if i == 0 else "a fake bridge",
            "tension": None,
            "open_questions": [],
        }
        for i, sid in enumerate(_ids_in(prompt_text))
    ]
    return {"cold_open_hook": "A fake hook.", "sections": sections, "dropped": []}


def _fake_section(prompt_text: str) -> dict:
    """Sized from the prompt's own "about N words" target, spread over enough
    alternating turns (>=3) that no turn nears the 600-character limit, so
    the draft passes validate_section at any episode length (D-40, D-59)."""
    target = _WORD_TARGET_RE.search(prompt_text)
    words = int(target.group(1)) if target else 120
    n_turns = max(3, math.ceil(words / 64))
    per_turn = max(1, round(words / n_turns / 8))  # _FAKE_SENTENCE is 8 words
    speakers = ["host_a", "host_b"]
    return {
        "turns": [
            {"speaker": speakers[i % 2], "text": _FAKE_SENTENCE * per_turn} for i in range(n_turns)
        ]
    }


def _fake_frame(prompt_text: str) -> dict:
    """A fixed, valid frame shape: script.py never puts story turns in the
    frame prompt (D-62), so there's nothing in the prompt to derive this
    from -- unlike outline/section, which key off the `[aNN]` ids or the
    word target actually rendered into their prompts."""
    return {
        "title": "Fake Episode",
        "summary": "A fake summary for testing.",
        "cold_open_turns": [{"speaker": "host_a", "text": _FAKE_SENTENCE * 2}],
        "preview_turns": [{"speaker": "host_b", "text": _FAKE_SENTENCE * 2}],
        "outro_turns": [{"speaker": "host_b", "text": _FAKE_SENTENCE * 3}],
    }


# Schemas whose fixture has to be derived from the prompt itself.
_FROM_PROMPT = {
    "Outline": _fake_outline,
    "SectionDraft": _fake_section,
    "FrameOutput": _fake_frame,
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
        if name in _FROM_PROMPT:
            parsed = schema.model_validate(_FROM_PROMPT[name](prompt.text))
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
