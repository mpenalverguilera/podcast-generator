"""Grounding check: a second LLM pass that fact-checks a written script
against the source article text each story section cited (podcast-script
skill "Grounding check" / ARCHITECTURE §5.5, docs/phases/04-quality.md Part
A). Deliberately stage-agnostic (no Episode/Session/Adapters here) so it's
unit-testable with a plain script + sources dict and any LLM -- script.py
owns wiring it into the scripting stage, persisting the flags, and logging
the extra `pipeline_steps` row (docs/DECISIONS.md D-30)."""

from app.adapters.llm.protocol import LLM
from app.config import Settings, get_settings
from app.prompts import load_prompt
from app.schemas import GroundingReport, Script, UnsupportedClaim, Usage

# One limit for what the section writer sees and what the grounder checks
# against, so a true fact from an article's tail isn't flagged just because
# the grounder was shown less of the source (docs/DECISIONS.md D-59).
SOURCE_CHARS = 12000


def _sections_block(
    script: Script, sources: dict[str, str], context_ids: dict[int, list[str]] | None = None
) -> str:
    """One block per section, indexed exactly as script.sections/turns are
    indexed (so a flagged claim's section_index/turn_index can be located
    directly): its turns, and -- for a "story" section -- the full text of
    every article it cited, truncated per source so the prompt stays bounded.
    A section with no source_ids (intro/outro) is marked as having none, so
    the model knows to flag any factual claim made there too.

    `context_ids[si]` (D-62), when given, is the *previous* story's own
    source ids: shown in a clearly separate, clearly labeled block so the
    checker can judge whether this section's bridge_in link back to it is
    accurate, without treating it as a valid source for this section's own
    new facts (see grounding_check.v3.md)."""
    context_ids = context_ids or {}
    blocks = []
    for si, section in enumerate(script.sections):
        turns = "\n".join(f"  turn {ti}: {t.text}" for ti, t in enumerate(section.turns))
        header = f"Section {si} ({section.kind}, story_id={section.story_id!r})"
        if section.source_ids:
            sources_text = "\n\n".join(
                f"[{sid}] {sources.get(sid, '(source text unavailable)')[:SOURCE_CHARS]}"
                for sid in section.source_ids
            )
            block = f"{header}\nSources:\n{sources_text}\nTurns:\n{turns}"
        else:
            block = f"{header} -- no sources, flag any factual claim here\nTurns:\n{turns}"
        extra = context_ids.get(si)
        if extra:
            extra_text = "\n\n".join(
                f"[{sid}] {sources.get(sid, '(source text unavailable)')[:SOURCE_CHARS]}"
                for sid in extra
            )
            block += (
                "\nPrevious story -- only to support a link back to it, not a source for this "
                f"section's own new facts:\n{extra_text}"
            )
        blocks.append(block)
    return "\n\n".join(blocks)


def check(
    script: Script,
    sources: dict[str, str],
    llm: LLM,
    settings: Settings | None = None,
    context_ids: dict[int, list[str]] | None = None,
) -> tuple[GroundingReport, Usage]:
    settings = settings or get_settings()
    prompt = load_prompt("grounding_check", sections=_sections_block(script, sources, context_ids))
    return llm.structured(
        prompt,
        GroundingReport,
        model=settings.model_grounding,
        reasoning=settings.model_grounding_reasoning,
    )


def format_issues(claims: list[UnsupportedClaim]) -> str:
    """Renders one section's flagged claims for the section_patch prompt.
    Only the turn index is shown: a patch call always sees one section."""
    return "\n".join(
        f'- turn {c.turn_index}: "{c.claim}" -- {c.reason}. Suggested fix: {c.suggested_fix}'
        for c in claims
    )


def sum_usage(usages: list[Usage]) -> Usage:
    """Sums sequential LLM call Usages into one: the grounding sub-step's own
    `pipeline_steps` row, and the scripting stage's returned Usage (outline +
    section writes + patches + polish). Calls are sequential, unlike rank.py's
    concurrent classification, so latency sums rather than maxes."""
    first = usages[0]
    return Usage(
        provider=first.provider,
        model=first.model,
        units_in=sum(u.units_in for u in usages),
        units_out=sum(u.units_out for u in usages),
        cost_usd=sum(u.cost_usd for u in usages),
        cost_is_estimate=first.cost_is_estimate,
        latency_ms=sum(u.latency_ms for u in usages),
        usage_source=first.usage_source,
    )
