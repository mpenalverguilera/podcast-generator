"""Scripting stage, v2 (docs/DECISIONS.md D-59). Still one pipeline stage and
one `Script` on episode.script, built in three steps:

1. OUTLINE: one call plans order, angle, facts and a word budget per section.
2. SECTIONS: written one at a time, each seeing the outline, only its own
   sources and the sections already written. Each is grounded against its
   own sources; if flagged, one patch call (draft + flags visible) and one
   re-check, keeping whichever version has fewer flags.
3. POLISH: one call writes the intro/outro, smooths the seams and adds audio
   tags. Only what it changed is grounded; a changed story section that gets
   flagged is reverted to its pre-polish draft.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.adapters.llm.protocol import LLM
from app.config import Settings, get_settings
from app.models import (
    Article,
    ArticleScore,
    ContentSource,
    Episode,
    EpisodeItem,
    PipelineStep,
    Preferences,
    StepStatus,
)
from app.pipeline import context, grounding
from app.pipeline.script_trace import ScriptTrace, claims_json, turns_diff_md, turns_md
from app.prompts import load_prompt
from app.schemas import (
    GroundingReport,
    InterestProfile,
    Outline,
    PolishedScript,
    RenderedPrompt,
    Script,
    ScriptStep,
    Section,
    SectionDraft,
    Turn,
    UnsupportedClaim,
    Usage,
)

logger = logging.getLogger(__name__)

# D-28 measured eleven_v3 at 973 words -> 428 s, about 136 words per minute
# once pauses and section breaks are counted; 150 overshot by ~19%.
_WORDS_PER_MINUTE = 135
_FRAME_SHARE = 0.12  # intro + outro share of the total budget
_MIN_FRAME_WORDS = 60
_INTRO_SHARE_OF_FRAME = 0.65
_SECTION_WORD_TOLERANCE = 0.25
_TOTAL_WORD_TOLERANCE = 0.20
_MAX_TURN_CHARS = 600
_MIN_STORY_TURNS = 3
_WORD_COUNT_ERROR = "word count"
_FOCUS_TOPIC = "focus"  # rank.py's synthetic topic for the focus request
_AUDIO_TAG_RE = re.compile(r"\[[^\]]*\]")

# Domains whose title-cased name reads wrong aloud. Anything else falls back
# to "strip www and the TLD, title-case the rest".
_OUTLET_OVERRIDES = {
    "apnews": "AP News",
    "arstechnica": "Ars Technica",
    "bbc": "BBC",
    "businessinsider": "Business Insider",
    "cnbc": "CNBC",
    "cnn": "CNN",
    "ft": "the Financial Times",
    "marketwatch": "MarketWatch",
    "npr": "NPR",
    "nytimes": "The New York Times",
    "techcrunch": "TechCrunch",
    "theguardian": "The Guardian",
    "theverge": "The Verge",
    "venturebeat": "VentureBeat",
    "washingtonpost": "The Washington Post",
    "wsj": "The Wall Street Journal",
}
_SECOND_LEVEL_SUFFIXES = {"co", "com", "org", "net", "gov", "ac"}


# --- small pure helpers -----------------------------------------------------


def short_id(article_id: int) -> str:
    return f"a{article_id}"


def strip_audio_tags(text: str) -> str:
    """Removes eleven_v3 audio tags like [laughs] and collapses the resulting
    double spaces -- used for the UI transcript (ARCHITECTURE §5.6) and to
    tell whether polish changed a section's words or only added tags."""
    return re.sub(r"\s+", " ", _AUDIO_TAG_RE.sub("", text)).strip()


def outlet_name(outlet: str | None) -> str:
    """A name the hosts can say: `www.reuters.com` -> `Reuters`,
    `news.bbc.co.uk` -> `BBC`. Leaves an already-readable name alone."""
    if not outlet or not outlet.strip():
        return "an unnamed outlet"
    raw = outlet.strip()
    host = urlsplit(raw).netloc if "://" in raw else raw
    host = host.split(":")[0].lower()
    if "." not in host:
        return raw
    labels = [label for label in host.split(".") if label]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL_SUFFIXES and len(labels[-1]) == 2:
        labels = labels[:-2]  # bbc.co.uk -> bbc
    else:
        labels = labels[:-1]  # reuters.com -> reuters
    if not labels:
        return raw
    name = labels[-1]  # the registrable label: finance.yahoo -> yahoo
    return _OUTLET_OVERRIDES.get(name, name.replace("-", " ").title())


def word_count(turns: list[Turn]) -> int:
    return sum(len(strip_audio_tags(t.text).split()) for t in turns)


def script_word_count(sections: list[Section]) -> int:
    return sum(word_count(s.turns) for s in sections)


def word_budget(target_minutes: int) -> tuple[int, int, int]:
    """(total, frame, story) words. The frame is the intro + outro."""
    total = target_minutes * _WORDS_PER_MINUTE
    frame = max(_MIN_FRAME_WORDS, round(_FRAME_SHARE * total))
    return total, frame, total - frame


def normalize_targets(targets: list[int], story_budget: int) -> list[int]:
    """Scales the outline's per-section target_words proportionally so they
    add up to the story budget (give or take rounding). The model's relative
    weights are kept; its arithmetic isn't trusted."""
    weights = [max(1, t) for t in targets]
    total = sum(weights)
    return [max(1, round(w * story_budget / total)) for w in weights]


def validate_outline(outline: Outline, selected_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not outline.sections:
        errors.append("the outline has no sections")
    story_ids = [s.story_id for s in outline.sections]
    if len(story_ids) != len(set(story_ids)):
        errors.append(f"story_ids are not unique: {story_ids}")

    seen: dict[str, int] = {}
    for s in outline.sections:
        if not s.source_ids:
            errors.append(f"section {s.story_id!r} has no source_ids")
        for sid in s.source_ids:
            seen[sid] = seen.get(sid, 0) + 1
    for d in outline.dropped:
        seen[d.source_id] = seen.get(d.source_id, 0) + 1

    for sid, count in seen.items():
        if sid not in selected_ids:
            errors.append(f"source id {sid!r} is not among the selected sources")
        elif count > 1:
            errors.append(f"source id {sid!r} is used {count} times; use each exactly once")
    for sid in sorted(selected_ids - seen.keys()):
        errors.append(f"source id {sid!r} is in no section and not in dropped")
    return errors


def validate_section(
    turns: list[Turn], host_names: list[str], target_words: int | None, *, is_story: bool = True
) -> list[str]:
    """Rules a schema can't express. Story sections also need >=3 turns, both
    hosts and a length within ±25% of target; intro/outro only the turn rules.
    A word-count error always starts with _WORD_COUNT_ERROR, so the caller can
    tell a length-only failure (accepted with a warning) from a real one."""
    errors: list[str] = []
    names = "|".join(re.escape(n) for n in [*host_names, "host_a", "host_b"])
    name_prefix = re.compile(rf"^\s*(?:{names})\s*:", re.IGNORECASE)
    if not turns:
        errors.append("the section has no turns")
    for i, turn in enumerate(turns):
        if not turn.text.strip():
            errors.append(f"turn {i} is empty")
        if len(turn.text) > _MAX_TURN_CHARS:
            errors.append(
                f"turn {i} is {len(turn.text)} characters, over the {_MAX_TURN_CHARS} limit"
            )
        if name_prefix.match(turn.text):
            errors.append(f"turn {i} starts with a speaker name; the speaker field says who talks")
    if is_story:
        if len(turns) < _MIN_STORY_TURNS:
            errors.append(f"only {len(turns)} turns; a story needs at least {_MIN_STORY_TURNS}")
        if {t.speaker for t in turns} != {"host_a", "host_b"}:
            errors.append("both hosts must speak in the section")
        if target_words:
            words = word_count(turns)
            lo = round(target_words * (1 - _SECTION_WORD_TOLERANCE))
            hi = round(target_words * (1 + _SECTION_WORD_TOLERANCE))
            if not lo <= words <= hi:
                errors.append(
                    f"{_WORD_COUNT_ERROR} {words} is outside {lo}-{hi} (target {target_words})"
                )
    return errors


def only_word_count_errors(errors: list[str]) -> bool:
    return bool(errors) and all(e.startswith(_WORD_COUNT_ERROR) for e in errors)


def check_polish(polished: PolishedScript, drafts: list[Section]) -> tuple[list[str], bool]:
    """(frame_errors, stories_ok). Frame errors mean no usable intro/outro;
    stories_ok is False when polish reordered, dropped or re-sourced a story
    section, in which case the drafts are kept for every story section."""
    secs = polished.sections
    frame_errors: list[str] = []
    if not secs or secs[0].kind != "intro":
        frame_errors.append('the first section must be the "intro"')
    if len(secs) < 2 or secs[-1].kind != "outro":
        frame_errors.append('the last section must be the "outro"')
    for s in (secs[0], secs[-1]) if len(secs) >= 2 else ():
        if s.kind in ("intro", "outro"):
            frame_errors += [
                f"{s.kind}: {e}" for e in validate_section(s.turns, [], None, is_story=False)
            ]

    stories = [s for s in secs if s.kind == "story"]
    stories_ok = (
        len(secs) == len(drafts) + 2
        and [(s.story_id, s.source_ids) for s in stories]
        == [(d.story_id, d.source_ids) for d in drafts]
        and all(len(t.text) <= _MAX_TURN_CHARS for s in stories for t in s.turns)
    )
    return frame_errors, stories_ok


def _spoken(section: Section) -> list[tuple[str, str]]:
    return [(t.speaker, strip_audio_tags(t.text)) for t in section.turns]


def changed_story_indices(drafts: list[Section], polished: list[Section]) -> list[int]:
    """Story sections whose words polish changed. Adding audio tags alone is
    not a change: tags carry no facts, so there is nothing to re-ground."""
    return [
        i for i, (d, p) in enumerate(zip(drafts, polished, strict=True)) if _spoken(d) != _spoken(p)
    ]


def revert_flagged(
    polished: list[Section], drafts: list[Section], flagged: set[int]
) -> list[Section]:
    """Polish must not add facts, so a changed story section that the
    grounder flags goes back to its already-grounded draft (tags and all
    polish edits in it are lost; they're optional)."""
    return [drafts[i] if i in flagged else s for i, s in enumerate(polished)]


def remap_flags(claims: list[UnsupportedClaim], index_map: list[int]) -> list[UnsupportedClaim]:
    """Grounding sees a small Script (one section, or intro + changed stories
    + outro), so its section_index is local. index_map[local] is the index in
    the final script (intro 0, story k is k). An out-of-range index from the
    model is pinned to the first checked section rather than dropped."""
    out = []
    for c in claims:
        local = c.section_index if 0 <= c.section_index < len(index_map) else 0
        out.append(c.model_copy(update={"section_index": index_map[local]}))
    return out


def apply_outline_order(outline: Outline, items: dict[str, EpisodeItem]) -> None:
    """Makes episode_items follow the audio: positions in outline order
    (dropped sources last) and every source of a section sharing its
    story_id. Story ids are renumbered s1..sN in outline order rather than
    copied from the first source's item, so a rescript after a merge can
    never produce two sections with the same story_id (D-59)."""
    position = 0
    for k, section in enumerate(outline.sections):
        section.story_id = f"s{k + 1}"
        for sid in section.source_ids:
            items[sid].position = position
            items[sid].story_id = section.story_id
            position += 1
    for j, dropped in enumerate(outline.dropped):
        items[dropped.source_id].position = position
        items[dropped.source_id].story_id = f"s{len(outline.sections) + j + 1}"
        position += 1


# --- per-episode context ----------------------------------------------------


@dataclass
class _Source:
    sid: str
    article: Article
    topic: str
    topic_label: str
    depth: str
    thin: bool
    outlet: str
    text: str  # header + body, truncated to grounding.SOURCE_CHARS: what writer and grounder see


def _topic_profile_line(profile: InterestProfile, topic: str) -> str:
    match = next((t for t in profile.topics if t.name == topic), None)
    if match is None:
        return f"{topic} (headlines)"
    parts = [f"{match.name} ({match.depth}): {match.description}"]
    if match.include:
        parts.append(f"Include: {', '.join(match.include)}")
    if match.exclude:
        parts.append(f"Exclude: {', '.join(match.exclude)}")
    return ". ".join(parts)


def _focus_label(focus_request: str | None) -> str:
    return f'Listener\'s request for this episode: "{focus_request or "(unspecified)"}"'


def _build_source(
    article: Article, topic: str, profile: InterestProfile, focus_request: str | None
) -> _Source:
    if topic == _FOCUS_TOPIC:
        label, depth = _focus_label(focus_request), "deep"
    else:
        match = next((t for t in profile.topics if t.name == topic), None)
        label, depth = topic, (match.depth if match else "headlines")
    thin = article.content_source == ContentSource.HIGHLIGHTS or not article.content
    outlet = outlet_name(article.outlet or urlsplit(article.url).netloc)
    date = article.published_at.date().isoformat() if article.published_at else "undated"
    kind = "highlights only: thin source" if thin else "full text"
    body = article.content or "\n".join(article.highlights or [])
    header = f"{outlet} — {date} — {article.title or '(untitled)'} ({kind})"
    text = f"{header}\n{body}"[: grounding.SOURCE_CHARS]
    return _Source(short_id(article.id), article, topic, label, depth, thin, outlet, text)


def _articles_block(sources: list[_Source]) -> str:
    lines = []
    for s in sources:
        date = s.article.published_at.date().isoformat() if s.article.published_at else "undated"
        kind = "highlights only" if s.thin else "full text"
        lines.append(
            f"[{s.sid}] {s.outlet} — {date} — {s.article.title or '(untitled)'} — "
            f"{s.topic_label} — {s.depth} — {kind}"
        )
        highlights = s.article.highlights or [(s.article.content or "")[:400]]
        lines += [f"    - {h.strip()}" for h in highlights if h and h.strip()]
    return "\n".join(lines)


def _render_turns(turns: list[Turn], names: dict[str, str]) -> str:
    return "\n".join(f"{names[t.speaker]}: {t.text}" for t in turns)


def _render_prior(prior: list[Section], names: dict[str, str]) -> str:
    if not prior:
        return "(none -- this is the first section)"
    return "\n\n".join(
        f"Section {k + 1}:\n{_render_turns(s.turns, names)}" for k, s in enumerate(prior)
    )


def _render_draft(turns: list[Turn], names: dict[str, str]) -> str:
    return "\n".join(f"turn {i} ({names[t.speaker]}): {t.text}" for i, t in enumerate(turns))


class ScriptingError(RuntimeError):
    """Carries the usage already spent, so the runner's failed-step row still
    records it and counts it toward the daily cap (D-56)."""

    def __init__(self, message: str, usage: Usage) -> None:
        super().__init__(message)
        self.usage = usage


@dataclass
class _Run:
    """What every sub-step needs, plus the running cost and trace."""

    episode_id: int
    llm: LLM
    settings: Settings
    names: dict[str, str]
    tone: str
    sources: dict[str, str]  # short id -> _Source.text
    script_usages: list[Usage] = field(default_factory=list)
    grounding_usages: list[Usage] = field(default_factory=list)
    trace: list[ScriptStep] = field(default_factory=list)
    prompt_versions: dict[str, int] = field(default_factory=dict)
    tracer: ScriptTrace = field(default_factory=lambda: ScriptTrace(None, 0))

    def write(
        self,
        prompt: RenderedPrompt,
        schema: type[BaseModel],
        label: str,
        section: int | None = None,
    ) -> tuple[BaseModel, Usage]:
        """One writing-model call (outline, section, patch, polish); the
        caller records it in the trace once it knows the words/errors.
        `label` only names the call in the optional on-disk trace."""
        result, usage = self.tracer.wrap(self.llm, label, section).structured(
            prompt,
            schema,
            model=self.settings.model_script,
            reasoning=self.settings.model_script_reasoning,
        )
        self.script_usages.append(usage)
        self.prompt_versions[prompt.name] = prompt.version
        return result, usage

    def ground(
        self, step: str, sections: list[Section], index_map: list[int], label: str
    ) -> list[UnsupportedClaim]:
        checked = Script(title="", summary="", sections=sections)
        section = index_map[0] if len(index_map) == 1 else None
        llm = self.tracer.wrap(self.llm, label, section)
        report, usage = grounding.check(checked, self.sources, llm, self.settings)
        assert isinstance(report, GroundingReport)
        self.grounding_usages.append(usage)
        self.prompt_versions["grounding_check"] = _grounding_prompt_version()
        claims = remap_flags(report.unsupported, index_map)
        self.record(step, usage, section=section, flags=len(claims))
        return claims

    def record(
        self,
        step: str,
        usage: Usage,
        *,
        section: int | None = None,
        words: int | None = None,
        flags: int | None = None,
        note: str | None = None,
    ) -> None:
        self.trace.append(
            ScriptStep(
                step=step,
                section=section,
                words=words,
                flags=flags,
                cost_usd=usage.cost_usd,
                latency_ms=usage.latency_ms,
                note=note,
            )
        )
        logger.info(
            "episode %s scripting %s section=%s words=%s flags=%s cost=$%.4f latency=%dms%s",
            self.episode_id,
            step,
            "-" if section is None else section,
            "-" if words is None else words,
            "-" if flags is None else flags,
            usage.cost_usd,
            usage.latency_ms,
            f" ({note})" if note else "",
        )

    def spent(self) -> Usage | None:
        usages = self.script_usages + self.grounding_usages
        return grounding.sum_usage(usages) if usages else None


def _grounding_prompt_version() -> int:
    return load_prompt("grounding_check", sections="").version


# --- sub-steps ----------------------------------------------------------------


def _patch(
    run: _Run,
    step: str,
    turns: list[Turn],
    issues: str,
    source_ids: list[str],
    target_words: int,
    final_index: int,
    *,
    is_story: bool,
    name: str,
) -> list[Turn]:
    sources = "\n\n".join(f"[{sid}] {run.sources[sid]}" for sid in source_ids)
    prompt = load_prompt(
        "section_patch",
        host_a=run.names["host_a"],
        host_b=run.names["host_b"],
        tone=run.tone,
        draft=_render_draft(turns, run.names),
        issues=issues,
        sources=sources,
        target_words=str(target_words),
        audio_tag_rule=(
            " No audio tags."
            if is_story
            else " Keep any audio tags like [laughs] where they are; add no new ones."
        ),
    )
    patched, usage = run.write(prompt, SectionDraft, f"{name}_{step}", final_index)
    assert isinstance(patched, SectionDraft)
    run.record(step, usage, section=final_index, words=word_count(patched.turns))
    return patched.turns


def _fix_flags(
    run: _Run,
    section: Section,
    grounded_as: list[str],
    flags: list[UnsupportedClaim],
    target_words: int,
    final_index: int,
    *,
    is_story: bool,
    name: str,
) -> tuple[Section, list[UnsupportedClaim]]:
    """One patch with the flags visible, one re-check; keeps whichever
    version has fewer flags. `grounded_as` is the source ids the section is
    checked against (its own for a story, all selected for intro/outro).
    `name` (s1, intro, ...) only names the optional trace files."""
    patched_file, reground_file = (
        (f"04_{name}_patched.md", f"05_{name}_regrounding.json")
        if is_story
        else (f"07_{name}_patched.md", f"07_{name}_regrounding.json")
    )
    turns = _patch(
        run,
        "patch",
        section.turns,
        grounding.format_issues(flags),
        grounded_as,
        target_words,
        final_index,
        is_story=is_story,
        name=name,
    )
    errors = validate_section(turns, list(run.names.values()), target_words, is_story=is_story)
    header = (
        f"# {name} patched -- {word_count(turns)} words (target {target_words})\n\n"
        f"Patched against {len(flags)} flag(s):\n{grounding.format_issues(flags)}\n\n"
    )
    if errors and not only_word_count_errors(errors):
        logger.warning(
            "episode %s section %s patch broke the section (%s); keeping the draft",
            run.episode_id,
            final_index,
            "; ".join(errors),
        )
        run.tracer.write_text(
            patched_file,
            header
            + f"**Patch rejected** ({'; '.join(errors)}); the draft was kept.\n\n"
            + turns_md(turns, run.names),
        )
        return section, flags
    candidate = section.model_copy(update={"turns": turns})
    run.tracer.write_text(
        patched_file,
        header
        + (f"Validation notes: {'; '.join(errors)}\n\n" if errors else "")
        + turns_diff_md(section.turns, turns, run.names),
    )
    new_flags = run.ground(
        "reground",
        [candidate.model_copy(update={"source_ids": grounded_as})],
        [final_index],
        f"{name}_reground",
    )
    kept = "patched" if len(new_flags) < len(flags) else "draft"
    run.tracer.write_json(
        reground_file,
        {
            "section": name,
            "checked_against": grounded_as,
            "flags_before": len(flags),
            "flags_after": len(new_flags),
            "kept": kept,
            "flags": claims_json(new_flags),
        },
    )
    if kept == "patched":
        return candidate, new_flags
    return section, flags


def _outline(
    run: _Run,
    sources: list[_Source],
    profile: InterestProfile,
    episode: Episode,
    headlines: list[str],
    story_budget: int,
) -> Outline:
    has_focus = any(s.topic == _FOCUS_TOPIC for s in sources)
    topic_lines = [f"- {_topic_profile_line(profile, t.name)}" for t in profile.topics]
    prompt = load_prompt(
        "outline",
        listener_profile="\n".join(topic_lines) or "- (no saved topics)",
        avoid=", ".join(profile.avoid) or "(nothing)",
        focus_line=(
            f"{_focus_label(episode.focus_request)} (treat it as a deep topic)."
            if episode.focus_request
            else "No special request for this episode."
        ),
        recent_headlines="; ".join(headlines) or "(none)",
        host_a=run.names["host_a"],
        host_b=run.names["host_b"],
        story_budget=str(story_budget),
        story_count=str(len(sources)),
        articles=_articles_block(sources),
        focus_order_rule=(
            " The listener's request comes first: open with the section built on the source "
            "whose topic is the listener's request."
            if has_focus
            else ""
        ),
    )
    selected_ids = {s.sid for s in sources}
    outline, usage = run.write(prompt, Outline, "outline")
    assert isinstance(outline, Outline)
    errors = validate_outline(outline, selected_ids)
    run.record("outline", usage, flags=len(errors) or None, note="; ".join(errors) or None)
    if errors:
        retry = prompt.model_copy(
            update={
                "text": prompt.text
                + "\n\nYour previous outline was:\n"
                + outline.model_dump_json(indent=2)
                + "\n\nIt had these problems -- return a corrected outline:\n"
                + "\n".join(f"- {e}" for e in errors)
            }
        )
        outline, usage = run.write(retry, Outline, "outline_retry")
        assert isinstance(outline, Outline)
        errors = validate_outline(outline, selected_ids)
        run.record("outline_retry", usage, flags=len(errors) or None)
        if errors:
            raise RuntimeError(f"outline invalid after retry: {'; '.join(errors)}")
    return outline


def write_section(
    run: _Run,
    outline: Outline,
    k: int,
    prior_sections: list[Section],
    source_by_id: dict[str, _Source],
    profile: InterestProfile,
) -> Section:
    """Writes story section k. Sequential by design: `prior_sections` are the
    sections already written, so this one can pick up where they left off. A
    parallel variant would pass [] for every section and run them in a
    thread pool; D-59 explains why that isn't built."""
    plan = outline.sections[k]
    primary = source_by_id[plan.source_ids[0]]
    if primary.topic == _FOCUS_TOPIC:
        topic_profile = f"{primary.topic_label} (deep)"
    else:
        topic_profile = _topic_profile_line(profile, primary.topic)
    prompt = load_prompt(
        "section_writer",
        host_a=run.names["host_a"],
        host_b=run.names["host_b"],
        tone=run.tone,
        outline=outline.model_dump_json(indent=2),
        section_number=str(k + 1),
        section_count=str(len(outline.sections)),
        section=plan.model_dump_json(indent=2),
        target_words=str(plan.target_words),
        depth=plan.depth,
        topic_profile=topic_profile,
        avoid=", ".join(profile.avoid) or "(nothing)",
        sources="\n\n".join(f"[{sid}] {run.sources[sid]}" for sid in plan.source_ids),
        prior_sections=_render_prior(prior_sections, run.names),
    )
    final_index = k + 1
    name = f"s{final_index}"
    draft, usage = run.write(prompt, SectionDraft, f"{name}_write", final_index)
    assert isinstance(draft, SectionDraft)
    turns = draft.turns
    host_names = list(run.names.values())
    errors = validate_section(turns, host_names, plan.target_words)
    run.record(
        "write",
        usage,
        section=final_index,
        words=word_count(turns),
        note="; ".join(errors) or None,
    )
    trace_md = [
        f"# {name} draft -- {plan.headline}\n",
        f"Sources: {', '.join(plan.source_ids)}. Depth: {plan.depth}.\n",
        f"First pass: {word_count(turns)} words (target {plan.target_words}, "
        f"±{round(_SECTION_WORD_TOLERANCE * 100)}%).",
        f"Validation: {'; '.join(errors) or 'ok'}\n",
        turns_md(turns, run.names),
    ]
    if errors:
        turns = _patch(
            run,
            "fix",
            turns,
            "\n".join(f"- {e}" for e in errors),
            plan.source_ids,
            plan.target_words,
            final_index,
            is_story=True,
            name=name,
        )
        errors = validate_section(turns, host_names, plan.target_words)
        trace_md += [
            f"\n## After the fix call: {word_count(turns)} words (target {plan.target_words})",
            f"Validation: {'; '.join(errors) or 'ok'}\n",
            turns_md(turns, run.names),
        ]
    run.tracer.write_text(f"02_{name}_draft.md", "\n".join(trace_md))
    if errors and not only_word_count_errors(errors):
        raise RuntimeError(f"section {final_index} invalid after a fix: {'; '.join(errors)}")
    if errors:
        logger.warning(
            "episode %s section %s accepted off-length: %s",
            run.episode_id,
            final_index,
            errors[0],
        )
    return Section(
        kind="story", story_id=plan.story_id, source_ids=list(plan.source_ids), turns=turns
    )


def _polish(
    run: _Run,
    outline: Outline,
    drafts: list[Section],
    total: int,
    frame: int,
    has_focus_section: bool,
    focus_request: str | None,
) -> PolishedScript:
    intro_words = round(frame * _INTRO_SHARE_OF_FRAME)
    prompt = load_prompt(
        "polish",
        host_a=run.names["host_a"],
        host_b=run.names["host_b"],
        tone=run.tone,
        total_budget=str(total),
        outline=outline.model_dump_json(indent=2),
        focus_line=(
            f'The listener asked about: "{focus_request}". The first story section answers it.'
            if has_focus_section
            else "There is no listener request to answer in this episode."
        ),
        focus_rule=(
            "Right after the AI-briefing line, say the listener asked about this (in natural "
            "words) and that's where we start."
            if has_focus_section
            else 'Do not say "you asked about..." -- there is no request to answer this time.'
        ),
        intro_words=str(intro_words),
        outro_words=str(frame - intro_words),
        drafts=json.dumps([d.model_dump() for d in drafts], indent=1),
    )
    polished, usage = run.write(prompt, PolishedScript, "polish")
    assert isinstance(polished, PolishedScript)
    frame_errors, _ = check_polish(polished, drafts)
    run.record(
        "polish",
        usage,
        words=script_word_count(polished.sections),
        note="; ".join(frame_errors) or None,
    )
    if frame_errors:
        retry = prompt.model_copy(
            update={
                "text": prompt.text
                + "\n\nYour previous attempt had these problems -- fix them:\n"
                + "\n".join(f"- {e}" for e in frame_errors)
            }
        )
        polished, usage = run.write(retry, PolishedScript, "polish_retry")
        assert isinstance(polished, PolishedScript)
        frame_errors, _ = check_polish(polished, drafts)
        run.record("polish_retry", usage, words=script_word_count(polished.sections))
        if frame_errors:
            raise RuntimeError(f"polish invalid after retry: {'; '.join(frame_errors)}")
    return polished


# --- the stage ---------------------------------------------------------------


def _load_inputs(
    episode: Episode, db: Session
) -> tuple[list[EpisodeItem], dict[int, Article], dict[int, str]]:
    items = list(
        db.scalars(
            select(EpisodeItem)
            .where(EpisodeItem.episode_id == episode.id)
            .order_by(EpisodeItem.position)
        )
    )
    if not items:
        raise RuntimeError(f"episode {episode.id} has no selected items; ranking produced nothing")
    ids = [i.article_id for i in items]
    articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(ids)))}
    scores = db.scalars(
        select(ArticleScore)
        .where(ArticleScore.episode_id == episode.id, ArticleScore.article_id.in_(ids))
        .order_by(ArticleScore.score.desc().nulls_last())
    )
    return items, articles, resolve_topics(list(scores))


def resolve_topics(scores: list[ArticleScore]) -> dict[int, str]:
    """The topic each selected article is covered under. An article can be
    scored under several topics; its best-scoring one wins -- except that the
    selected article with the best "focus" score is the focus story, even if
    it scored as high or higher under a profile topic, because rank.py fills
    its focus slot with exactly that article (D-59)."""
    ranked = sorted(scores, key=lambda s: s.score if s.score is not None else -1, reverse=True)
    topics: dict[int, str] = {}
    for s in ranked:
        if s.topic:
            topics.setdefault(s.article_id, s.topic)
    focus = next((s for s in ranked if s.topic == _FOCUS_TOPIC), None)
    if focus is not None:
        topics[focus.article_id] = _FOCUS_TOPIC
    return topics


# --- optional trace files (script_trace.py) -----------------------------------


def _inputs_md(
    episode: Episode,
    profile: InterestProfile,
    names: dict[str, str],
    tone: str,
    headlines: list[str],
    sources: list[_Source],
    total: int,
    frame: int,
) -> str:
    lines = [
        f"# Episode {episode.id} -- scripting inputs\n",
        "## Profile",
        *[f"- {_topic_profile_line(profile, t.name)}" for t in profile.topics],
        f"- Avoid: {', '.join(profile.avoid) or '(nothing)'}",
        f"\nFocus request: {episode.focus_request or '(none)'}",
        f"Hosts: {names['host_a']} (host_a), {names['host_b']} (host_b). Tone: {tone}",
        f"Recent headlines: {'; '.join(headlines) or '(none)'}\n",
        f"## Budget\nTarget {episode.target_minutes} min x {_WORDS_PER_MINUTE} wpm = {total} "
        f"words: frame {frame} (intro {round(frame * _INTRO_SHARE_OF_FRAME)}), "
        f"stories {total - frame}\n",
        f"## Selected articles ({len(sources)})",
        "| id | outlet | date | title | topic | content |",
        "|---|---|---|---|---|---|",
    ]
    for s in sources:
        date = s.article.published_at.date().isoformat() if s.article.published_at else "undated"
        content = "highlights only" if s.thin else f"full text ({len(s.text)} chars shown)"
        title = (s.article.title or "(untitled)").replace("|", "/")
        lines.append(f"| {s.sid} | {s.outlet} | {date} | {title} | {s.topic_label} | {content} |")
    return "\n".join(lines)


def _outline_md(outline: Outline, raw_targets: list[int]) -> str:
    lines = [f"# Outline\n\nCold open: {outline.cold_open_hook}\n"]
    for s, raw in zip(outline.sections, raw_targets, strict=True):
        lines += [
            f"## {s.story_id}: {s.headline}",
            f"- sources: {', '.join(s.source_ids)} | topic: {s.topic_label} | depth: {s.depth}",
            f"- target words: {s.target_words} (model asked for {raw})",
            f"- angle: {s.angle}",
            f"- why the listener cares: {s.why_listener_cares}",
            f"- bridge in: {s.bridge_in or '-'}",
            "- key facts:",
            *[f"  - {f}" for f in s.key_facts],
            f"- must not cover: {'; '.join(s.must_not_cover) or '-'}\n",
        ]
    if outline.dropped:
        lines.append("## Dropped")
        lines += [f"- {d.source_id}: {d.reason}" for d in outline.dropped]
    return "\n".join(lines)


def _polish_md(
    polished: PolishedScript,
    drafts: list[Section],
    stories_ok: bool,
    changed: list[int],
    names: dict[str, str],
) -> str:
    lines = [
        f"# Polish -- {polished.title}\n",
        f"Summary: {polished.summary}\n",
        f"Polished words: {script_word_count(polished.sections)}. "
        f"Story sections with changed words (grounded again): "
        f"{', '.join(f's{i + 1}' for i in changed) or 'none'}.",
    ]
    if not stories_ok:
        lines.append(
            "\n**Polish changed the story sections' structure; its story sections were "
            "discarded and the drafts kept.**"
        )
    stories = iter(drafts)
    for s in polished.sections:
        if s.kind != "story":
            lines += [f"\n## {s.kind} (new, {word_count(s.turns)} words)", turns_md(s.turns, names)]
            continue
        draft = next(stories, None)
        label = f"story {s.story_id}"
        if draft is None:
            lines += [f"\n## {label} (no matching draft)", turns_md(s.turns, names)]
            continue
        kind = (
            "words changed"
            if _spoken(draft) != _spoken(s)
            else ("tags only" if draft.turns != s.turns else "unchanged")
        )
        lines += [
            f"\n## {label} ({kind}, {word_count(draft.turns)} → {word_count(s.turns)} words)",
            turns_diff_md(draft.turns, s.turns, names),
        ]
    return "\n".join(lines)


def _final_md(script: Script, names: dict[str, str], total: int) -> str:
    words = script_word_count(script.sections)
    lines = [f"# {script.title}\n", script.summary, ""]
    for i, s in enumerate(script.sections):
        label = s.kind if s.kind != "story" else f"story {s.story_id} ({', '.join(s.source_ids)})"
        lines += [f"## {i}. {label} -- {word_count(s.turns)} words"]
        lines += [f"**{names[t.speaker]}:** {t.text}\n" for t in s.turns]
    lines.append(
        f"---\nTotal: {words} words vs budget {total} ({words - total:+d}, "
        f"{(words - total) / total:+.0%}; tolerance ±{round(_TOTAL_WORD_TOLERANCE * 100)}%)"
    )
    return "\n".join(lines)


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    items, articles, topics = _load_inputs(episode, db)
    profile = context.load_profile(db, episode.user_id)
    headlines = context.recent_headlines(db, episode)

    prefs = db.get(Preferences, episode.user_id)
    names = {
        "host_a": (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex",
        "host_b": (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam",
    }
    tone = (prefs.tone if prefs and prefs.tone else None) or "warm, informed, a little playful"

    sources = [
        _build_source(
            articles[i.article_id],
            topics.get(i.article_id, "general"),
            profile,
            episode.focus_request,
        )
        for i in items
    ]
    source_by_id = {s.sid: s for s in sources}
    items_by_sid = {short_id(i.article_id): i for i in items}
    run_ = _Run(
        episode_id=episode.id,
        llm=adapters.llm,
        settings=settings,
        names=names,
        tone=tone,
        sources={s.sid: s.text for s in sources},
        tracer=ScriptTrace(settings.script_trace_dir, episode.id),
    )
    total, frame, story_budget = word_budget(episode.target_minutes)
    if run_.tracer.enabled:
        run_.tracer.write_text(
            "00_inputs.md",
            _inputs_md(episode, profile, names, tone, headlines, sources, total, frame),
        )

    try:
        script, initial_flags, final_flags = _script(
            run_,
            episode,
            sources,
            source_by_id,
            items_by_sid,
            profile,
            headlines,
            total,
            frame,
            story_budget,
        )
    except Exception as exc:
        spent = run_.spent()
        if spent is None:
            raise
        raise ScriptingError(str(exc), spent) from exc

    episode.script = script.model_dump()
    episode.title = script.title
    episode.summary = script.summary
    episode.grounding_flags_initial = [c.model_dump() for c in initial_flags]
    episode.grounding_flags_final = [c.model_dump() for c in final_flags]
    episode.prompt_versions = {**(episode.prompt_versions or {}), **run_.prompt_versions}

    grounding_total = grounding.sum_usage(run_.grounding_usages)
    db.add(
        PipelineStep(
            episode_id=episode.id,
            stage="grounding",
            status=StepStatus.SUCCESS,
            provider=grounding_total.provider,
            model=grounding_total.model,
            units_in=grounding_total.units_in,
            units_out=grounding_total.units_out,
            cost_usd=grounding_total.cost_usd,
            cost_is_estimate=grounding_total.cost_is_estimate,
            usage_source=grounding_total.usage_source,
            latency_ms=grounding_total.latency_ms,
        )
    )
    script_total = grounding.sum_usage(run_.script_usages)
    logger.info(
        "episode %s scripted %d words (budget %d) in %d sections, cost=$%.4f, "
        "grounding flags initial=%d final=%d cost=$%.4f",
        episode.id,
        script_word_count(script.sections),
        total,
        len(script.sections),
        script_total.cost_usd,
        len(initial_flags),
        len(final_flags),
        grounding_total.cost_usd,
    )
    return script_total


def _script(
    run_: _Run,
    episode: Episode,
    sources: list[_Source],
    source_by_id: dict[str, _Source],
    items_by_sid: dict[str, EpisodeItem],
    profile: InterestProfile,
    headlines: list[str],
    total: int,
    frame: int,
    story_budget: int,
) -> tuple[Script, list[UnsupportedClaim], list[UnsupportedClaim]]:
    # 1. Outline
    outline = _outline(run_, sources, profile, episode, headlines, story_budget)
    raw_targets = [s.target_words for s in outline.sections]
    targets = normalize_targets(raw_targets, story_budget)
    for plan, target in zip(outline.sections, targets, strict=True):
        plan.target_words = target
    apply_outline_order(outline, items_by_sid)
    run_.tracer.write_json(
        "01_outline.json", {"outline": outline.model_dump(), "model_target_words": raw_targets}
    )
    run_.tracer.write_text("01_outline.md", _outline_md(outline, raw_targets))

    # 2. Sections, sequentially, each grounded against its own sources
    drafts: list[Section] = []
    flags_initial: dict[int, list[UnsupportedClaim]] = {}
    flags_final: dict[int, list[UnsupportedClaim]] = {}
    for k, plan in enumerate(outline.sections):
        section = write_section(run_, outline, k, drafts, source_by_id, profile)
        final_index = k + 1
        name = f"s{final_index}"
        flags = run_.ground("ground", [section], [final_index], f"{name}_ground")
        run_.tracer.write_json(
            f"03_{name}_grounding.json",
            {"section": name, "checked_against": section.source_ids, "flags": claims_json(flags)},
        )
        flags_initial[final_index] = flags
        if flags:
            section, flags = _fix_flags(
                run_,
                section,
                section.source_ids,
                flags,
                plan.target_words,
                final_index,
                is_story=True,
                name=name,
            )
        flags_final[final_index] = flags
        drafts.append(section)

    # 3. Polish, then ground only what it changed
    has_focus_section = any(
        source_by_id[sid].topic == _FOCUS_TOPIC for p in outline.sections for sid in p.source_ids
    )
    polished = _polish(
        run_, outline, drafts, total, frame, has_focus_section, episode.focus_request
    )
    intro = polished.sections[0].model_copy(update={"story_id": None, "source_ids": []})
    outro = polished.sections[-1].model_copy(update={"story_id": None, "source_ids": []})
    _, stories_ok = check_polish(polished, drafts)
    if stories_ok:
        stories = [s for s in polished.sections if s.kind == "story"]
    else:
        logger.warning(
            "episode %s polish changed the story sections' structure; keeping the drafts",
            episode.id,
        )
        run_.record("polish_discarded", Usage(provider="none"), note="kept drafts for stories")
        stories = drafts
    changed = changed_story_indices(drafts, stories)
    run_.tracer.write_text(
        "06_polish.md", _polish_md(polished, drafts, stories_ok, changed, run_.names)
    )

    n = len(drafts)
    all_ids = [s.sid for s in sources]
    checked = [
        intro.model_copy(update={"source_ids": all_ids}),
        *[stories[i] for i in changed],
        outro.model_copy(update={"source_ids": all_ids}),
    ]
    index_map = [0, *[i + 1 for i in changed], n + 1]
    polish_flags = run_.ground("ground_polish", checked, index_map, "polish_ground")
    by_index: dict[int, list[UnsupportedClaim]] = {}
    for c in polish_flags:
        by_index.setdefault(c.section_index, []).append(c)

    reverted = {i for i in changed if by_index.get(i + 1)}
    for i in sorted(reverted):
        run_.record(
            "revert",
            Usage(provider="none"),
            section=i + 1,
            flags=len(by_index[i + 1]),
            note="polish changed facts; reverted to the grounded draft",
        )
    stories = revert_flagged(stories, drafts, reverted)

    frame_budget = {0: round(frame * _INTRO_SHARE_OF_FRAME)}
    frame_budget[n + 1] = frame - frame_budget[0]
    fixed: dict[int, Section] = {0: intro, n + 1: outro}
    for idx in (0, n + 1):
        flags = by_index.get(idx, [])
        flags_initial[idx] = flags
        if flags:
            fixed[idx], flags = _fix_flags(
                run_,
                fixed[idx],
                all_ids,
                flags,
                frame_budget[idx],
                idx,
                is_story=False,
                name="intro" if idx == 0 else "outro",
            )
        flags_final[idx] = flags

    if run_.tracer.enabled:

        def sec_name(idx: int) -> str:
            return "intro" if idx == 0 else "outro" if idx == n + 1 else f"s{idx}"

        run_.tracer.write_json(
            "07_polish_grounding.json",
            {
                "polish_stories_kept": stories_ok,
                "checked": [
                    {"section": sec_name(idx), "index": idx, "source_ids": s.source_ids}
                    for idx, s in zip(index_map, checked, strict=True)
                ],
                "not_checked_unchanged": [f"s{i + 1}" for i in range(n) if i not in changed],
                "flags": [
                    {"section": sec_name(c.section_index), **c.model_dump()} for c in polish_flags
                ],
                "reverted": [
                    {
                        "section": f"s{i + 1}",
                        "flagged_turns": sorted({c.turn_index for c in by_index[i + 1]}),
                        "claims": [c.claim for c in by_index[i + 1]],
                    }
                    for i in sorted(reverted)
                ],
                "frame_flags_after_patch": {
                    "intro": claims_json(flags_final[0]),
                    "outro": claims_json(flags_final[n + 1]),
                },
            },
        )

    sections = [fixed[0], *stories, fixed[n + 1]]
    words = script_word_count(sections)
    if abs(words - total) > _TOTAL_WORD_TOLERANCE * total:
        logger.warning(
            "episode %s script is %d words against a %d-word budget (outside ±%d%%)",
            episode.id,
            words,
            total,
            round(_TOTAL_WORD_TOLERANCE * 100),
        )
    script = Script(
        title=polished.title,
        summary=polished.summary,
        sections=sections,
        outline=outline,
        trace=run_.trace,
    )
    if run_.tracer.enabled:
        run_.tracer.write_text("08_final.md", _final_md(script, run_.names, total))

    def flatten(d: dict[int, list[UnsupportedClaim]]) -> list[UnsupportedClaim]:
        return [c for idx in sorted(d) for c in d[idx]]

    return script, flatten(flags_initial), flatten(flags_final)
