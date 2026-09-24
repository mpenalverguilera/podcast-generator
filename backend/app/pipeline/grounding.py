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
from app.schemas import GroundingReport, Script, Usage

_MAX_SOURCE_CHARS = 4000


def _sections_block(script: Script, sources: dict[str, str]) -> str:
    """One block per section, indexed exactly as script.sections/turns are
    indexed (so a flagged claim's section_index/turn_index can be located
    directly): its turns, and -- for a "story" section -- the full text of
    every article it cited, truncated per source so the prompt stays bounded.
    A section with no source_ids (intro/outro) is marked as having none, so
    the model knows to flag any factual claim made there too."""
    blocks = []
    for si, section in enumerate(script.sections):
        turns = "\n".join(f"  turn {ti}: {t.text}" for ti, t in enumerate(section.turns))
        header = f"Section {si} ({section.kind}, story_id={section.story_id!r})"
        if section.source_ids:
            sources_text = "\n\n".join(
                f"[{sid}] {sources.get(sid, '(source text unavailable)')[:_MAX_SOURCE_CHARS]}"
                for sid in section.source_ids
            )
            blocks.append(f"{header}\nSources:\n{sources_text}\nTurns:\n{turns}")
        else:
            blocks.append(f"{header} -- no sources, flag any factual claim here\nTurns:\n{turns}")
    return "\n\n".join(blocks)


def check(
    script: Script, sources: dict[str, str], llm: LLM, settings: Settings | None = None
) -> tuple[GroundingReport, Usage]:
    settings = settings or get_settings()
    prompt = load_prompt("grounding_check", sections=_sections_block(script, sources))
    return llm.structured(
        prompt,
        GroundingReport,
        model=settings.model_grounding,
        reasoning=settings.model_grounding_reasoning,
    )


def format_issues(report: GroundingReport) -> str:
    """Renders a GroundingReport as the block appended to the script_writer
    prompt for the one allowed revision pass (script.py), the same shape as
    script.py's own validation-error retry text."""
    return "\n".join(
        f'- section {c.section_index} turn {c.turn_index}: "{c.claim}" -- {c.reason}. '
        f"Suggested fix: {c.suggested_fix}"
        for c in report.unsupported
    )


def sum_usage(usages: list[Usage]) -> Usage:
    """Sums a sequence of grounding-check call Usages into the one
    `pipeline_steps` row script.py writes for the grounding sub-step. Calls
    are sequential (initial check, then an optional re-check), unlike rank.py's
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
