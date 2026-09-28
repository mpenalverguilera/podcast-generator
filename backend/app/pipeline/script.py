"""Scripting stage, v2.1 (docs/DECISIONS.md D-59, D-62, D-63). Still one
pipeline stage and one `Script` on episode.script, built in three steps:

1. OUTLINE: one call plans order, angle, facts and a per-section word
   ceiling, and may drop a source it finds is actually stale.
2. SECTIONS: written one at a time, each seeing the outline, only its own
   sources and the sections already written. Each is grounded against its
   own sources (plus the previous section's, for context on its bridge); if
   flagged, one patch call is always kept, and only the turns it actually
   changed are re-checked.
3. FRAME: one call writes only the intro's cold open + preview and the
   outro. Story sections pass through untouched.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
from app.pipeline.budget import WORDS_PER_MINUTE, frame_word_targets, word_budget
from app.pipeline.script_trace import ScriptTrace, claims_json, turns_diff_md, turns_md
from app.prompts import load_prompt
from app.schemas import (
    FrameOutput,
    GroundingReport,
    InterestProfile,
    Outline,
    RenderedPrompt,
    Script,
    ScriptStep,
    Section,
    SectionDraft,
    TagFix,
    Turn,
    UnsupportedClaim,
    Usage,
)

logger = logging.getLogger(__name__)

_MAX_WORDS_SCALE_CAP = 1.3  # D-62: scaling a section's ceiling UP is capped; scaling down isn't
_MAX_WORDS_OVERAGE = 0.10  # D-62: only exceeding the ceiling by >10% is a validation error
_MAX_WORDS_FLOOR = 0.5  # D-62: under half the ceiling is a warning only, never an error
_TOTAL_WORD_TOLERANCE = 0.20
_MAX_TURN_CHARS = 600
_MIN_STORY_TURNS = 3
_WORD_COUNT_ERROR = "word count"
_FOCUS_TOPIC = "focus"  # rank.py's synthetic topic for the focus request
_AUDIO_TAG_RE = re.compile(r"\[[^\]]*\]")
# D-65: the outline reads this much of each full-text source's body (was a
# 500-char staleness snippet), so its take and key facts come from the
# article's evidence and caveats, not only Exa's highlights.
_OUTLINE_BODY_CHARS = 3000

# D-62: narrated-personalization and template-closer phrases, banned outright
# in every story section; the frame's intro may say "you asked about" once,
# checked separately by count in validate_frame.
_BANNED_PHRASES = (
    "if you follow",
    "for anyone following",
    "for fans of",
    "as you asked",
    "you asked about",
    "it'll be interesting to see",
)

# Domains whose title-cased name reads wrong aloud. Only used for the
# human-readable review export now (eval/scripts_v2/export_review.py) --
# D-62 stopped feeding this to the model; see _raw_domain.
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
    tell whether a patch changed a turn's words or only its tags."""
    return re.sub(r"\s+", " ", _AUDIO_TAG_RE.sub("", text)).strip()


def outlet_name(outlet: str | None) -> str:
    """A name for a human reading the review export: `www.reuters.com` ->
    `Reuters`, `news.bbc.co.uk` -> `BBC`. Leaves an already-readable name
    alone. D-62 stopped passing this to the model -- concatenated domains
    read badly aloud (`Techcompanynews`, `Mlwires`); the model now sees the
    raw domain and infers a natural spoken name itself (see _raw_domain)."""
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


def _raw_domain(outlet: str | None, url: str) -> str:
    """The bare domain shown to the model (D-62): `https://www.reuters.com/x`
    or `www.reuters.com` both become `www.reuters.com`. No override, no
    title-casing -- the writer is told to infer a natural spoken name from
    this itself, or say "one report" / "a trade site" when it can't."""
    raw = (outlet or url or "").strip()
    host = urlsplit(raw).netloc if "://" in raw else raw
    return host.split(":")[0] or raw or "an unknown site"


def word_count(turns: list[Turn]) -> int:
    return sum(len(strip_audio_tags(t.text).split()) for t in turns)


def script_word_count(sections: list[Section]) -> int:
    return sum(word_count(s.turns) for s in sections)


def scale_max_words(max_words: list[int], story_budget: int) -> list[int]:
    """Scales the outline's per-section `max_words` ceilings by one factor so
    the episode fits the story budget (D-62). Scaling *up* is capped at 1.3x
    -- an outline that asked for well under budget stays a set of short
    sections rather than being stretched thin (D-59 episode 15710: an
    unlimited stretch took 150 words to 238, x1.58). Scaling *down* is
    unlimited: an outline that over-asked just gets proportionally thinner."""
    weights = [max(1, w) for w in max_words]
    total = sum(weights)
    factor = min(story_budget / total, _MAX_WORDS_SCALE_CAP) if total else 1.0
    return [max(1, round(w * factor)) for w in weights]


def banned_phrase_hits(text: str, *, exclude: frozenset[str] = frozenset()) -> list[str]:
    low = text.lower()
    return [p for p in _BANNED_PHRASES if p in low and p not in exclude]


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
    turns: list[Turn], host_names: list[str], max_words: int | None, *, is_story: bool = True
) -> list[str]:
    """Rules a schema can't express. Story sections also need >=3 turns and
    both hosts; every section is checked for the no-name-prefix, turn-length
    and banned-phrase rules. `max_words`, when given, is a ceiling: only
    exceeding it by more than `_MAX_WORDS_OVERAGE` is an error (D-62) -- a
    word-count error always starts with _WORD_COUNT_ERROR, so the caller can
    tell a length-only failure (accepted with a warning) from a real one.
    Falling under half of `max_words` is never an error here; the caller logs
    it as a warning instead (see `floor_warning`)."""
    errors: list[str] = []
    names = "|".join(re.escape(n) for n in [*host_names, "host_a", "host_b"])
    name_prefix = re.compile(rf"^\s*(?:{names})\s*:", re.IGNORECASE)
    # The frame's intro may say "you asked about" once (validate_frame checks
    # the count); a story section never gets to say it at all.
    exclude = frozenset() if is_story else frozenset({"you asked about"})
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
        hits = banned_phrase_hits(turn.text, exclude=exclude)
        if hits:
            errors.append(f"turn {i} uses a banned phrase: {', '.join(hits)}")
    if is_story:
        if len(turns) < _MIN_STORY_TURNS:
            errors.append(f"only {len(turns)} turns; a story needs at least {_MIN_STORY_TURNS}")
        if {t.speaker for t in turns} != {"host_a", "host_b"}:
            errors.append("both hosts must speak in the section")
    if max_words:
        words = word_count(turns)
        ceiling = round(max_words * (1 + _MAX_WORDS_OVERAGE))
        if words > ceiling:
            errors.append(
                f"{_WORD_COUNT_ERROR} {words} exceeds the {max_words}-word maximum (over {ceiling})"
            )
    return errors


def floor_warning(words: int, max_words: int | None) -> str | None:
    """D-62: falling under half of a section's word ceiling is worth logging
    (the writer may be under-using a rich source) but is never a validation
    error -- a short section is a fine outcome, not a bug."""
    if not max_words:
        return None
    floor = round(max_words * _MAX_WORDS_FLOOR)
    if words < floor:
        return f"{words} words is under half the {max_words}-word maximum ({floor})"
    return None


def only_word_count_errors(errors: list[str]) -> bool:
    return bool(errors) and all(e.startswith(_WORD_COUNT_ERROR) for e in errors)


# D-69: phrases that say the personalization out loud; the frame must never use them.
_REQUEST_NARRATION = (
    "you asked about",
    "you asked for",
    "you wanted to know",
    "you wanted to hear",
    "as you asked",
    "as you requested",
    "your request",
)


def validate_frame(frame: FrameOutput, host_names: list[str]) -> list[str]:
    """Pure checks on the frame call's output (D-62, replacing check_polish):
    turn-count shape, the shared turn rules on the intro (cold open + preview
    combined) and the outro, and that the intro never narrates the listener's
    request (D-69: "you asked about" was allowed once with a focus section
    until then; the user doesn't want the personalization said aloud)."""
    errors: list[str] = []
    if not (1 <= len(frame.cold_open_turns) <= 2):
        errors.append(f"cold_open_turns must be 1-2 turns, got {len(frame.cold_open_turns)}")
    if not frame.preview_turns:
        errors.append("preview_turns must have at least 1 turn")
    if not (1 <= len(frame.outro_turns) <= 2):
        errors.append(f"outro_turns must be 1-2 turns, got {len(frame.outro_turns)}")
    intro_turns = [*frame.cold_open_turns, *frame.preview_turns]
    errors += [
        f"intro: {e}" for e in validate_section(intro_turns, host_names, None, is_story=False)
    ]
    errors += [
        f"outro: {e}" for e in validate_section(frame.outro_turns, host_names, None, is_story=False)
    ]
    intro_text = " ".join(t.text.lower() for t in intro_turns)
    said = [p for p in _REQUEST_NARRATION if p in intro_text]
    if said:
        errors.append(f"the intro must not narrate the listener's request: {', '.join(said)}")
    return errors


def changed_turn_indices(before: list[Turn], after: list[Turn]) -> list[int]:
    """Turns a patch actually changed, tags stripped (D-62): the re-check
    after a patch only re-spends grounding on what moved. If the patch
    changed the turn count -- it shouldn't, but nothing stops it -- every
    turn counts as changed, since position-by-position diffing wouldn't mean
    anything anymore."""
    if len(before) != len(after):
        return list(range(len(after)))
    return [
        i
        for i, (b, a) in enumerate(zip(before, after, strict=True))
        if strip_audio_tags(b.text) != strip_audio_tags(a.text)
    ]


def remap_flags(claims: list[UnsupportedClaim], index_map: list[int]) -> list[UnsupportedClaim]:
    """Grounding sees a small Script (one or two sections), so its
    section_index is local. index_map[local] is the index in the final
    script (intro 0, story k is k). An out-of-range index from the model is
    pinned to the first checked section rather than dropped."""
    out = []
    for c in claims:
        local = c.section_index if 0 <= c.section_index < len(index_map) else 0
        out.append(c.model_copy(update={"section_index": index_map[local]}))
    return out


def remap_turn_subset(
    claims: list[UnsupportedClaim], final_index: int, turn_ids: list[int]
) -> list[UnsupportedClaim]:
    """Maps flags from a re-check of a turn *subset* (built as one section
    containing exactly `turn_ids`' turns, in order) back to the section's
    real final_index/turn_index (D-62's changed-turns-only re-check). An
    out-of-range turn_index from the model is pinned to the first checked
    turn rather than dropped."""
    out = []
    for c in claims:
        ti = (
            turn_ids[c.turn_index]
            if 0 <= c.turn_index < len(turn_ids)
            else (turn_ids[0] if turn_ids else 0)
        )
        out.append(c.model_copy(update={"section_index": final_index, "turn_index": ti}))
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
    outlet = _raw_domain(article.outlet, article.url)
    date = article.published_at.date().isoformat() if article.published_at else "undated"
    kind = "highlights only: thin source" if thin else "full text"
    header = f"{outlet} — {date} — {article.title or '(untitled)'} ({kind})"
    highlights = "\n".join(f"- {h.strip()}" for h in article.highlights or [] if h and h.strip())
    # D-66: the outline plans key_facts from highlights + body, so the writer and
    # grounder must see the highlights too. They come first so the SOURCE_CHARS
    # cut drops the tail of a long body, never the passages Exa picked out.
    if article.content and highlights:
        text = f"{header}\nHighlights:\n{highlights}\n\nArticle text:\n{article.content}"
    else:
        text = f"{header}\n{article.content or highlights}"
    text = text[: grounding.SOURCE_CHARS]
    return _Source(short_id(article.id), article, topic, label, depth, thin, outlet, text)


def _articles_block(sources: list[_Source]) -> str:
    """Besides highlights, each full-text source gets the first
    `_OUTLINE_BODY_CHARS` of its body (D-65; D-62 showed only a 500-char
    snippet). The opening is where a byline or photo caption date usually
    sits, so the outline can still catch a source whose *stored* date is
    wrong (D-62: article a655's caption read "Saturday Feb. 28, 2026" while
    its stored published_at was the day of the fetch); the rest is the
    evidence the outline's take and key facts are planned from."""
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
        if not s.thin and s.article.content:
            body = " ".join(s.article.content[:_OUTLINE_BODY_CHARS].split())
            if body:
                lines.append(f"    - article text (first {_OUTLINE_BODY_CHARS} chars): {body}")
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
        """One writing-model call (outline, section, patch, frame); the
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
        self,
        step: str,
        sections: list[Section],
        index_map: list[int],
        label: str,
        context_by_local_index: dict[int, list[str]] | None = None,
    ) -> tuple[list[UnsupportedClaim], list[TagFix]]:
        """Fact flags and audio-tag fixes (D-68), both remapped to final
        section indices. Tag fixes are counted in the step's note, never in
        `flags`, so the fact-flag numbers stay comparable across versions."""
        checked = Script(title="", summary="", sections=sections)
        section = index_map[0] if len(index_map) == 1 else None
        llm = self.tracer.wrap(self.llm, label, section)
        report, usage = grounding.check(
            checked, self.sources, llm, self.settings, context_by_local_index
        )
        assert isinstance(report, GroundingReport)
        self.grounding_usages.append(usage)
        self.prompt_versions["grounding_check"] = _grounding_prompt_version()
        claims = remap_flags(report.unsupported, index_map)
        tag_fixes = [
            f.model_copy(update={"section_index": index_map[f.section_index]})
            for f in report.tag_fixes
            if 0 <= f.section_index < len(index_map)
        ]
        note = f"tag fixes proposed: {len(tag_fixes)}" if tag_fixes else None
        self.record(step, usage, section=section, flags=len(claims), note=note)
        return claims, tag_fixes

    def ground_turns(
        self,
        step: str,
        section: Section,
        turn_ids: list[int],
        final_index: int,
        label: str,
        context_ids: list[str] | None = None,
    ) -> list[UnsupportedClaim]:
        """Re-grounds only `turn_ids` of `section` after a patch (D-62), so a
        re-check doesn't re-spend on turns the patch never touched."""
        subset = section.model_copy(update={"turns": [section.turns[i] for i in turn_ids]})
        checked = Script(title="", summary="", sections=[subset])
        llm = self.tracer.wrap(self.llm, label, final_index)
        context = {0: context_ids} if context_ids else None
        report, usage = grounding.check(checked, self.sources, llm, self.settings, context)
        assert isinstance(report, GroundingReport)
        self.grounding_usages.append(usage)
        self.prompt_versions["grounding_check"] = _grounding_prompt_version()
        claims = remap_turn_subset(report.unsupported, final_index, turn_ids)
        self.record(step, usage, section=final_index, flags=len(claims))
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
    context_ids: list[str] | None = None,
    enforce_ceiling: bool = True,
) -> tuple[Section, list[UnsupportedClaim]]:
    """One patch, **always kept** (D-62: no draft-vs-patch comparison -- a tie
    in flag counts used to make the old code keep the draft with its
    original problem, seen live in the D-59 traces on episode 15710). Only
    the turns the patch actually changed are re-checked; a flagged turn the
    patch left untouched stays flagged in the result (`residual`).
    `grounded_as` is the source ids the section is checked against (its own
    for a story, all selected for the frame); `context_ids`, when given, is
    the previous story's sources, shown read-only for judging a bridge.
    `name` (s1, intro, ...) only names the optional trace files."""
    patched_file, reground_file = (
        (f"04_{name}_patched.md", f"05_{name}_regrounding.json")
        if is_story
        else (f"07_{name}_patched.md", f"07_{name}_regrounding.json")
    )
    original_turns = section.turns
    turns = _patch(
        run,
        "patch",
        original_turns,
        grounding.format_issues(flags),
        grounded_as,
        target_words,
        final_index,
        name=name,
    )
    validate_words = target_words if enforce_ceiling else None
    errors = validate_section(turns, list(run.names.values()), validate_words, is_story=is_story)
    header = (
        f"# {name} patched -- {word_count(turns)} words (target {target_words})\n\n"
        f"Patched against {len(flags)} flag(s):\n{grounding.format_issues(flags)}\n\n"
    )
    if errors and not only_word_count_errors(errors):
        logger.warning(
            "episode %s section %s patch has problems (%s); keeping it anyway (D-62)",
            run.episode_id,
            final_index,
            "; ".join(errors),
        )
    candidate = section.model_copy(update={"turns": turns})
    run.tracer.write_text(
        patched_file,
        header
        + (f"Validation notes: {'; '.join(errors)}\n\n" if errors else "")
        + turns_diff_md(original_turns, turns, run.names),
    )
    changed = changed_turn_indices(original_turns, turns)
    unfixed = [f for f in flags if f.turn_index not in changed]
    new_flags = (
        run.ground_turns(
            "reground", candidate, changed, final_index, f"{name}_reground", context_ids
        )
        if changed
        else []
    )
    residual = unfixed + new_flags
    run.tracer.write_json(
        reground_file,
        {
            "section": name,
            "checked_against": grounded_as,
            "changed_turns": changed,
            "flags_before": len(flags),
            "flags_after": len(residual),
            "flags": claims_json(residual),
        },
    )
    return candidate, residual


def _outline(
    run: _Run,
    sources: list[_Source],
    profile: InterestProfile,
    episode: Episode,
    headlines: list[str],
    story_budget: int,
    today: str,
    window_start: str,
) -> Outline:
    has_focus = any(s.topic == _FOCUS_TOPIC for s in sources)
    topic_lines = [f"- {_topic_profile_line(profile, t.name)}" for t in profile.topics]
    prompt = load_prompt(
        "outline",
        today=today,
        window_start=window_start,
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
    # D-68: radio-style tease and payoff. The cold open teases the hook; the
    # first story pays it off with a callback instead of restating it as new.
    first_section_rule = (
        "This is the first section. The episode's cold open just teased: "
        f'"{outline.cold_open_hook}". Pay it off: call back to it in a few words '
        '("those ten seconds...", "that head start") and then give the full detail -- '
        "don't announce it as if the listener hadn't heard it."
        if k == 0
        else ""
    )
    prompt = load_prompt(
        "section_writer",
        host_a=run.names["host_a"],
        host_b=run.names["host_b"],
        tone=run.tone,
        outline=outline.model_dump_json(indent=2),
        section_number=str(k + 1),
        section_count=str(len(outline.sections)),
        section=plan.model_dump_json(indent=2),
        max_words=str(plan.max_words),
        depth=plan.depth,
        first_section_rule=first_section_rule,
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
    errors = validate_section(turns, host_names, plan.max_words)
    note = "; ".join(errors) or floor_warning(word_count(turns), plan.max_words)
    run.record("write", usage, section=final_index, words=word_count(turns), note=note)
    trace_md = [
        f"# {name} draft -- {plan.headline}\n",
        f"Sources: {', '.join(plan.source_ids)}. Depth: {plan.depth}.\n",
        f"First pass: {word_count(turns)} words (max {plan.max_words}, "
        f"+{round(_MAX_WORDS_OVERAGE * 100)}%/-{round(_MAX_WORDS_FLOOR * 100)}%).",
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
            plan.max_words,
            final_index,
            name=name,
        )
        errors = validate_section(turns, host_names, plan.max_words)
        trace_md += [
            f"\n## After the fix call: {word_count(turns)} words (max {plan.max_words})",
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


def _frame(
    run: _Run,
    outline: Outline,
    frame_budget: int,
    has_focus_section: bool,
    focus_request: str | None,
) -> FrameOutput:
    intro_words, outro_words = frame_word_targets(frame_budget)
    prompt = load_prompt(
        "frame",
        host_a=run.names["host_a"],
        host_b=run.names["host_b"],
        tone=run.tone,
        outline=outline.model_dump_json(indent=2),
        focus_line=(
            f'The listener asked about: "{focus_request}". The first story section answers it.'
            if has_focus_section
            else "There is no listener request to answer in this episode."
        ),
        focus_rule=(
            "The first story answers the listener's request: start the preview with it, like any "
            'other story -- never say it was requested (no "you asked about", "you wanted to '
            'know", "your request").'
            if has_focus_section
            else 'Do not say "you asked about..." -- there is no request to answer this time.'
        ),
        intro_words=str(intro_words),
        outro_words=str(outro_words),
    )
    frame_out, usage = run.write(prompt, FrameOutput, "frame")
    assert isinstance(frame_out, FrameOutput)
    host_names = list(run.names.values())
    errors = validate_frame(frame_out, host_names)
    frame_words = word_count(
        [*frame_out.cold_open_turns, *frame_out.preview_turns, *frame_out.outro_turns]
    )
    run.record("frame", usage, words=frame_words, note="; ".join(errors) or None)
    if errors:
        retry = prompt.model_copy(
            update={
                "text": prompt.text
                + "\n\nYour previous attempt had these problems -- fix them:\n"
                + "\n".join(f"- {e}" for e in errors)
            }
        )
        frame_out, usage = run.write(retry, FrameOutput, "frame_retry")
        assert isinstance(frame_out, FrameOutput)
        errors = validate_frame(frame_out, host_names)
        run.record("frame_retry", usage)
        if errors:
            raise RuntimeError(f"frame invalid after retry: {'; '.join(errors)}")
    return frame_out


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
    today: str,
    window_start: str,
) -> str:
    lines = [
        f"# Episode {episode.id} -- scripting inputs\n",
        "## Profile",
        *[f"- {_topic_profile_line(profile, t.name)}" for t in profile.topics],
        f"- Avoid: {', '.join(profile.avoid) or '(nothing)'}",
        f"\nFocus request: {episode.focus_request or '(none)'}",
        f"Hosts: {names['host_a']} (host_a), {names['host_b']} (host_b). Tone: {tone}",
        f"Recent headlines: {'; '.join(headlines) or '(none)'}",
        f"Today: {today}. Window start: {window_start}.\n",
        f"## Budget\nTarget {episode.target_minutes} min x {WORDS_PER_MINUTE} wpm = {total} "
        f"words: frame {frame}, stories up to {total - frame}\n",
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


def _outline_md(outline: Outline, raw_max_words: list[int]) -> str:
    lines = [f"# Outline\n\nCold open: {outline.cold_open_hook}\n"]
    for s, raw in zip(outline.sections, raw_max_words, strict=True):
        lines += [
            f"## {s.story_id}: {s.headline}",
            f"- sources: {', '.join(s.source_ids)} | topic: {s.topic_label} | depth: {s.depth}",
            f"- max words: {s.max_words} (model asked for {raw})",
            f"- take (angle): {s.angle}",
            f"- stakes: {s.stakes}",
            f"- tension: {s.tension or '-'}",
            f"- open questions: {'; '.join(s.open_questions) or '-'}",
            f"- bridge in: {s.bridge_in or '-'}",
            "- key facts:",
            *[f"  - {f}" for f in s.key_facts],
            f"- must not cover: {'; '.join(s.must_not_cover) or '-'}\n",
        ]
    if outline.dropped:
        lines.append("## Dropped")
        lines += [f"- {d.source_id}: {d.reason}" for d in outline.dropped]
    return "\n".join(lines)


def _frame_md(
    frame_out: FrameOutput, final_intro: Section, final_outro: Section, names: dict[str, str]
) -> str:
    return "\n".join(
        [
            f"# Frame -- {frame_out.title}\n",
            f"Summary: {frame_out.summary}\n",
            "## Intro (final)",
            turns_md(final_intro.turns, names),
            "\n## Outro (final)",
            turns_md(final_outro.turns, names),
        ]
    )


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
    today = datetime.now(UTC).date().isoformat()
    window_start = episode.window_start.date().isoformat()
    if run_.tracer.enabled:
        run_.tracer.write_text(
            "00_inputs.md",
            _inputs_md(
                episode, profile, names, tone, headlines, sources, total, frame, today, window_start
            ),
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
            today,
            window_start,
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
    frame_budget: int,
    story_budget: int,
    today: str,
    window_start: str,
) -> tuple[Script, list[UnsupportedClaim], list[UnsupportedClaim]]:
    # 1. Outline
    outline = _outline(
        run_, sources, profile, episode, headlines, story_budget, today, window_start
    )
    raw_max_words = [s.max_words for s in outline.sections]
    scaled = scale_max_words(raw_max_words, story_budget)
    for plan, words in zip(outline.sections, scaled, strict=True):
        plan.max_words = words
    apply_outline_order(outline, items_by_sid)
    run_.tracer.write_json(
        "01_outline.json", {"outline": outline.model_dump(), "model_max_words": raw_max_words}
    )
    run_.tracer.write_text("01_outline.md", _outline_md(outline, raw_max_words))

    # 2. Sections, sequentially, each grounded against its own sources plus
    #    the previous story's, shown read-only for judging its bridge (D-62).
    drafts: list[Section] = []
    flags_initial: dict[int, list[UnsupportedClaim]] = {}
    flags_final: dict[int, list[UnsupportedClaim]] = {}
    for k, plan in enumerate(outline.sections):
        section = write_section(run_, outline, k, drafts, source_by_id, profile)
        final_index = k + 1
        name = f"s{final_index}"
        context_ids = drafts[-1].source_ids if drafts else None
        context = {0: context_ids} if context_ids else None
        flags, tag_fixes = run_.ground(
            "ground", [section], [final_index], f"{name}_ground", context
        )
        section, applied_tags = grounding.apply_tag_fixes(section, tag_fixes)
        run_.tracer.write_json(
            f"03_{name}_grounding.json",
            {
                "section": name,
                "checked_against": section.source_ids,
                "context_previous_story": context_ids or [],
                "flags": claims_json(flags),
                "tag_fixes": [f.model_dump() for f in applied_tags],
            },
        )
        flags_initial[final_index] = flags
        if flags:
            section, flags = _fix_flags(
                run_,
                section,
                section.source_ids,
                flags,
                plan.max_words,
                final_index,
                is_story=True,
                name=name,
                context_ids=context_ids,
            )
        flags_final[final_index] = flags
        drafts.append(section)

    # 3. Frame: intro (cold open + preview) and outro. Story sections pass
    #    through untouched (D-62).
    has_focus_section = any(
        source_by_id[sid].topic == _FOCUS_TOPIC for p in outline.sections for sid in p.source_ids
    )
    frame_out = _frame(run_, outline, frame_budget, has_focus_section, episode.focus_request)
    intro_work = [*frame_out.cold_open_turns, *frame_out.preview_turns]
    outro_work = list(frame_out.outro_turns)

    n = len(drafts)
    all_ids = [s.sid for s in sources]
    checked = [
        Section(kind="intro", turns=intro_work, source_ids=all_ids),
        Section(kind="outro", turns=outro_work, source_ids=all_ids),
    ]
    frame_flags, frame_tag_fixes = run_.ground("ground_frame", checked, [0, n + 1], "frame_ground")
    intro_checked, _ = grounding.apply_tag_fixes(
        checked[0], [f for f in frame_tag_fixes if f.section_index == 0]
    )
    outro_checked, _ = grounding.apply_tag_fixes(
        checked[1], [f for f in frame_tag_fixes if f.section_index == n + 1]
    )
    intro_work, outro_work = list(intro_checked.turns), list(outro_checked.turns)
    by_index: dict[int, list[UnsupportedClaim]] = {}
    for c in frame_flags:
        by_index.setdefault(c.section_index, []).append(c)

    flags_initial[0] = by_index.get(0, [])
    flags_initial[n + 1] = by_index.get(n + 1, [])
    flags_final[0] = flags_initial[0]
    flags_final[n + 1] = flags_initial[n + 1]

    intro_target, outro_target = frame_word_targets(frame_budget)
    if by_index.get(0):
        intro_section, flags_final[0] = _fix_flags(
            run_,
            Section(kind="intro", turns=intro_work, source_ids=all_ids),
            all_ids,
            by_index[0],
            intro_target,
            0,
            is_story=False,
            name="intro",
            enforce_ceiling=False,
        )
        intro_work = intro_section.turns
    if by_index.get(n + 1):
        outro_section, flags_final[n + 1] = _fix_flags(
            run_,
            Section(kind="outro", turns=outro_work, source_ids=all_ids),
            all_ids,
            by_index[n + 1],
            outro_target,
            n + 1,
            is_story=False,
            name="outro",
            enforce_ceiling=False,
        )
        outro_work = outro_section.turns

    final_intro = Section(kind="intro", turns=intro_work)
    final_outro = Section(kind="outro", turns=outro_work)

    run_.tracer.write_text(
        "06_frame.md", _frame_md(frame_out, final_intro, final_outro, run_.names)
    )
    if run_.tracer.enabled:
        run_.tracer.write_json(
            "07_frame_grounding.json",
            {
                "checked": [
                    {"section": "intro", "source_ids": all_ids},
                    {"section": "outro", "source_ids": all_ids},
                ],
                "flags": [
                    {"section": "intro" if c.section_index == 0 else "outro", **c.model_dump()}
                    for c in frame_flags
                ],
                "flags_after_patch": {
                    "intro": claims_json(flags_final[0]),
                    "outro": claims_json(flags_final[n + 1]),
                },
            },
        )

    sections = [final_intro, *drafts, final_outro]
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
        title=frame_out.title,
        summary=frame_out.summary,
        sections=sections,
        outline=outline,
        trace=run_.trace,
    )
    if run_.tracer.enabled:
        run_.tracer.write_text("08_final.md", _final_md(script, run_.names, total))

    def flatten(d: dict[int, list[UnsupportedClaim]]) -> list[UnsupportedClaim]:
        return [c for idx in sorted(d) for c in d[idx]]

    return script, flatten(flags_initial), flatten(flags_final)
