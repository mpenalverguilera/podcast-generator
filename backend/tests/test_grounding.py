from app.pipeline import grounding
from app.schemas import (
    ClaimCheck,
    GroundingChecks,
    RenderedPrompt,
    Script,
    Section,
    Turn,
    UnsupportedClaim,
    Usage,
)

_PLANTED_NUMBER = "9999888"


def _turn(speaker: str, text: str) -> Turn:
    return Turn(speaker=speaker, text=text)


class _GroundingOnlyLLM:
    """Just enough of the LLM protocol for grounding.check() unit tests: a
    canned GroundingChecks, with the rendered prompt text captured so tests
    can assert on what the model actually saw."""

    def __init__(self, checks: GroundingChecks) -> None:
        self._checks = checks
        self.last_prompt: RenderedPrompt | None = None

    def structured(self, prompt, schema, model, reasoning):
        assert schema is GroundingChecks
        self.last_prompt = prompt
        return self._checks, Usage(provider="fake", model=model, cost_usd=0.002, latency_ms=7)


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


# --- grounding.check() / format_issues() / sum_usage() -- pure unit tests ---


def test_check_sends_source_text_and_no_sources_note_to_the_model() -> None:
    scripted = _clean_script("a1")
    llm = _GroundingOnlyLLM(GroundingChecks(checks=[]))

    report, usage = grounding.check(scripted, {"a1": "the real source text"}, llm)

    assert report.unsupported == []
    assert usage.cost_usd == 0.002
    assert "the real source text" in llm.last_prompt.text
    assert "no sources" in llm.last_prompt.text  # the intro/outro sections


def test_check_labels_context_sources_as_previous_story_only() -> None:
    """D-62: a section's own sources are still what it's graded against;
    context_ids adds the previous story's sources in a clearly separate,
    clearly labeled block, so the checker can judge a bridge-in link without
    treating it as license for a new fact."""
    scripted = _clean_script("a1")
    llm = _GroundingOnlyLLM(GroundingChecks(checks=[]))

    grounding.check(
        scripted,
        {"a1": "this section's own source", "a0": "the previous story's source"},
        llm,
        context_ids={1: ["a0"]},  # section 1 ("story") gets a0 as context
    )

    prompt = llm.last_prompt.text
    assert "the previous story's source" in prompt
    assert "not a source for this section's own new facts" in prompt
    # The intro (section 0) got no context -- only section 1's own block does.
    intro_block = prompt.split("Section 0 (", 1)[1].split("Section 1 (", 1)[0]
    assert "not a source for this section's own new facts" not in intro_block


def test_check_flags_a_planted_false_number_not_in_the_source() -> None:
    """Acceptance A: plant one false number in a copy of the script and prove
    the check flags it, using a fake/stub LLM (a real run is done separately
    against a real episode for the demo, per docs/phases/04-quality.md)."""
    planted_script = _script_with_marker("a1")
    llm = _GroundingOnlyLLM(
        GroundingChecks(
            checks=[
                ClaimCheck(
                    section_index=1,
                    turn_index=0,
                    claim=f"revenue hit ${_PLANTED_NUMBER}",
                    evidence="not in the source",
                    verdict="unsupported",
                    suggested_fix="drop the figure",
                ),
                ClaimCheck(
                    section_index=1,
                    turn_index=0,
                    claim="that's a big quarter",
                    evidence="a host's judgment, no new specific",
                    verdict="take",
                    suggested_fix="",
                ),
            ]
        )
    )

    report, _usage = grounding.check(
        planted_script, {"a1": "the real source text, no dollar figures at all"}, llm
    )

    assert len(report.unsupported) == 1  # the "take" row is not a flag
    assert report.unsupported[0].reason == "not in the source"
    assert _PLANTED_NUMBER in llm.last_prompt.text  # the planted claim reached the model
    assert report.unsupported[0].section_index == 1
    assert report.unsupported[0].turn_index == 0


def test_format_issues_renders_one_line_per_claim() -> None:
    claims = [
        UnsupportedClaim(
            section_index=1,
            turn_index=0,
            claim="X",
            reason="not in sources",
            suggested_fix="drop X",
        ),
        UnsupportedClaim(
            section_index=1, turn_index=3, claim="Y", reason="wrong outlet", suggested_fix="fix Y"
        ),
    ]
    lines = grounding.format_issues(claims).splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("- turn 0:") and "drop X" in lines[0]
    assert lines[1].startswith("- turn 3:") and "fix Y" in lines[1]


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
