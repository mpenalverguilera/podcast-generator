from sqlalchemy import select

from app.adapters import Adapters
from app.models import Article, ContentSource, EpisodeItem, PipelineStep
from app.pipeline import grounding, script
from app.pipeline.script import short_id
from app.schemas import (
    GroundingReport,
    RenderedPrompt,
    Script,
    Section,
    Turn,
    UnsupportedClaim,
    Usage,
)
from tests.conftest import make_user_with_episode

_PLANTED_NUMBER = "9999888"


def _turn(speaker: str, text: str) -> Turn:
    return Turn(speaker=speaker, text=text)


class _GroundingOnlyLLM:
    """Just enough of the LLM protocol for grounding.check() unit tests: a
    canned GroundingReport, with the rendered prompt text captured so tests
    can assert on what the model actually saw."""

    def __init__(self, report: GroundingReport) -> None:
        self._report = report
        self.last_prompt: RenderedPrompt | None = None

    def structured(self, prompt, schema, model, reasoning):
        assert schema is GroundingReport
        self.last_prompt = prompt
        return self._report, Usage(provider="fake", model=model, cost_usd=0.002, latency_ms=7)


def _script_with_marker(source_id: str) -> Script:
    # "word " * 41 + the 9-word planted-figure sentence = 50 words, matching
    # the other two 50-word sections -- 150 words total, the middle of
    # target_minutes=1's [128, 173] budget window (see test_script.py).
    planted = (
        f"The company said revenue hit ${_PLANTED_NUMBER} dollars last quarter. " + "word " * 41
    )
    filler = "word " * 50
    return Script(
        title="t",
        summary="s",
        sections=[
            Section(kind="intro", source_ids=[], turns=[_turn("host_a", filler)]),
            Section(
                kind="story",
                story_id="s1",
                source_ids=[source_id],
                turns=[_turn("host_b", planted)],
            ),
            Section(kind="outro", source_ids=[], turns=[_turn("host_a", filler)]),
        ],
    )


def _clean_script(source_id: str) -> Script:
    filler = "word " * 50
    return Script(
        title="t",
        summary="s",
        sections=[
            Section(kind="intro", source_ids=[], turns=[_turn("host_a", filler)]),
            Section(
                kind="story", story_id="s1", source_ids=[source_id], turns=[_turn("host_b", filler)]
            ),
            Section(kind="outro", source_ids=[], turns=[_turn("host_a", filler)]),
        ],
    )


class _ScriptedLLM:
    """LLM stand-in for script.run() integration tests. Script calls are
    answered from a fixed queue (initial write, then the grounding revision
    if one happens); GroundingReport calls flag a claim iff the rendered
    prompt contains the planted marker, so the fixture scripts above drive
    the check deterministically without a real model."""

    def __init__(self, scripts: list[Script]) -> None:
        self._scripts = list(scripts)
        self.grounding_call_count = 0

    def structured(self, prompt, schema, model, reasoning):
        if schema is GroundingReport:
            self.grounding_call_count += 1
            unsupported = []
            if _PLANTED_NUMBER in prompt.text:
                unsupported = [
                    UnsupportedClaim(
                        section_index=1,
                        turn_index=0,
                        claim=f"revenue hit ${_PLANTED_NUMBER}",
                        reason="that figure does not appear in the source article",
                        suggested_fix="speak generally about revenue instead of citing a figure",
                    )
                ]
            return GroundingReport(unsupported=unsupported), Usage(
                provider="fake", model=model, cost_usd=0.001, latency_ms=5, usage_source="fake"
            )
        if schema is Script:
            return self._scripts.pop(0), Usage(
                provider="fake", model=model, cost_usd=0.01, latency_ms=10, usage_source="fake"
            )
        raise NotImplementedError(schema)


def _episode_with_one_article(db, *, target_minutes: int = 1):
    episode = make_user_with_episode(db)
    episode.target_minutes = target_minutes
    article = Article(
        url_hash="hash-1",
        url="https://example.com/1",
        outlet="Outlet A",
        title="Company reports results",
        content="The company reported strong quarterly results and steady growth.",
        content_source=ContentSource.TEXT,
    )
    db.add(article)
    db.flush()
    db.add(EpisodeItem(episode_id=episode.id, article_id=article.id, position=0, story_id="s1"))
    db.flush()
    return episode, article


# --- grounding.check() / format_issues() / sum_usage() -- pure unit tests ---


def test_check_sends_source_text_and_no_sources_note_to_the_model() -> None:
    scripted = _clean_script("a1")
    llm = _GroundingOnlyLLM(GroundingReport(unsupported=[]))

    report, usage = grounding.check(scripted, {"a1": "the real source text"}, llm)

    assert report.unsupported == []
    assert usage.cost_usd == 0.002
    assert "the real source text" in llm.last_prompt.text
    assert "no sources" in llm.last_prompt.text  # the intro/outro sections


def test_check_flags_a_planted_false_number_not_in_the_source() -> None:
    """Acceptance A: plant one false number in a copy of the script and prove
    the check flags it, using a fake/stub LLM (a real run is done separately
    against a real episode for the demo, per docs/phases/04-quality.md)."""
    planted_script = _script_with_marker("a1")
    llm = _GroundingOnlyLLM(
        GroundingReport(
            unsupported=[
                UnsupportedClaim(
                    section_index=1,
                    turn_index=0,
                    claim=f"revenue hit ${_PLANTED_NUMBER}",
                    reason="not in the source",
                    suggested_fix="drop the figure",
                )
            ]
        )
    )

    report, _usage = grounding.check(
        planted_script, {"a1": "the real source text, no dollar figures at all"}, llm
    )

    assert len(report.unsupported) == 1
    assert _PLANTED_NUMBER in llm.last_prompt.text  # the planted claim reached the model
    assert report.unsupported[0].section_index == 1
    assert report.unsupported[0].turn_index == 0


def test_format_issues_renders_one_line_per_claim() -> None:
    report = GroundingReport(
        unsupported=[
            UnsupportedClaim(
                section_index=1,
                turn_index=0,
                claim="X",
                reason="not in sources",
                suggested_fix="drop X",
            ),
            UnsupportedClaim(
                section_index=2,
                turn_index=1,
                claim="Y",
                reason="wrong outlet",
                suggested_fix="fix Y",
            ),
        ]
    )
    text = grounding.format_issues(report)
    lines = text.splitlines()
    assert len(lines) == 2
    assert "section 1 turn 0" in lines[0] and "drop X" in lines[0]
    assert "section 2 turn 1" in lines[1] and "fix Y" in lines[1]


def test_sum_usage_sums_cost_and_latency_keeps_provider_and_model() -> None:
    usages = [
        Usage(
            provider="openai",
            model="gpt-6-luna",
            units_in=10,
            units_out=5,
            cost_usd=0.01,
            latency_ms=100,
        ),
        Usage(
            provider="openai",
            model="gpt-6-luna",
            units_in=8,
            units_out=4,
            cost_usd=0.02,
            latency_ms=80,
        ),
    ]
    total = grounding.sum_usage(usages)
    assert total.provider == "openai"
    assert total.model == "gpt-6-luna"
    assert total.units_in == 18
    assert total.units_out == 9
    assert abs(total.cost_usd - 0.03) < 1e-9
    assert total.latency_ms == 180


# --- script.run() integration: the grounding sub-step end to end ---


def test_script_run_flags_then_clears_on_a_clean_revision(db) -> None:
    episode, article = _episode_with_one_article(db)
    sid = short_id(article.id)
    llm = _ScriptedLLM([_script_with_marker(sid), _clean_script(sid)])
    adapters = Adapters(search=None, llm=llm, classifier=None, tts=None)  # type: ignore[arg-type]

    script.run(episode, adapters, db)

    assert len(episode.grounding_flags_initial) == 1
    assert episode.grounding_flags_initial[0]["claim"] == f"revenue hit ${_PLANTED_NUMBER}"
    assert episode.grounding_flags_final == []  # the revision cleared it
    assert llm.grounding_call_count == 2  # initial check + one re-check after revision
    # The revised (clean) script is what actually got persisted.
    assert _PLANTED_NUMBER not in str(episode.script)

    steps = db.scalars(
        select(PipelineStep).where(
            PipelineStep.episode_id == episode.id, PipelineStep.stage == "grounding"
        )
    ).all()
    assert len(steps) == 1
    # Both grounding.check() calls' cost is on this one row (0.001 x 2).
    assert abs(float(steps[0].cost_usd) - 0.002) < 1e-9


def test_script_run_keeps_original_script_when_revision_is_invalid(db) -> None:
    episode, article = _episode_with_one_article(db)
    sid = short_id(article.id)
    original = _script_with_marker(sid)
    invalid_revision = Script(
        title="t",
        summary="s",
        # No source_ids on a story section -- fails validate_script, so the
        # revision must be rejected and the pre-revision script kept.
        sections=[
            Section(kind="story", story_id="s1", source_ids=[], turns=[_turn("host_a", "hi")])
        ],
    )
    llm = _ScriptedLLM([original, invalid_revision])
    adapters = Adapters(search=None, llm=llm, classifier=None, tts=None)  # type: ignore[arg-type]

    script.run(episode, adapters, db)

    assert len(episode.grounding_flags_initial) == 1
    assert episode.grounding_flags_final == episode.grounding_flags_initial  # no re-check happened
    assert llm.grounding_call_count == 1  # revision was rejected before a re-check
    assert _PLANTED_NUMBER in str(episode.script)  # original script was kept
