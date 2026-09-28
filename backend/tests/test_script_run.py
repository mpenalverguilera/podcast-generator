"""script.run() end to end with a stub LLM: outline -> sections with
per-section grounding and patching -> frame (intro/outro only, story sections
untouched). The stub answers from FakeLLM unless a test queues something, and
its grounding check flags any turn containing the planted marker."""

import json
import math
import re

import pytest
from sqlalchemy import select

from app.adapters import Adapters
from app.adapters.llm.fake import FakeLLM
from app.config import get_settings
from app.models import Article, ArticleScore, ContentSource, EpisodeItem, PipelineStep
from app.pipeline import script
from app.pipeline.script import ScriptingError, scale_max_words, short_id, word_budget
from app.schemas import (
    ClaimCheck,
    FrameOutput,
    GroundingChecks,
    Outline,
    RenderedPrompt,
    SectionDraft,
    Turn,
    Usage,
)
from tests.conftest import make_user_with_episode

_MARKER = "9999888"
_SECTION_RE = re.compile(r"^Section (\d+) \(")
_TURN_RE = re.compile(r"^  turn (\d+): (.*)$")


class _StubLLM:
    def __init__(self, *, outlines=(), sections=(), frame=None) -> None:
        self._fake = FakeLLM()
        self.outlines = list(outlines)
        self.sections = list(sections)
        self.frame = frame  # callable(FrameOutput) -> FrameOutput
        self.calls: list[tuple[str, str]] = []

    def structured(self, prompt, schema, model, reasoning):
        name = schema.__name__
        self.calls.append((name, prompt.text))
        usage = Usage(provider="fake", model=model, cost_usd=0.001, latency_ms=5)
        if schema is GroundingChecks:
            return _flag_marker(prompt.text), usage
        if schema is Outline and self.outlines:
            return self.outlines.pop(0), usage
        if schema is SectionDraft and self.sections:
            queued = self.sections.pop(0)
            if queued is not None:
                return queued, usage
        parsed, _ = self._fake.structured(prompt, schema, model, reasoning)
        if schema is FrameOutput and self.frame:
            parsed = self.frame(parsed)
        return parsed, usage

    def prompts(self, schema_name: str) -> list[str]:
        return [text for name, text in self.calls if name == schema_name]


def _flag_marker(prompt_text: str) -> GroundingChecks:
    """Reads the grounding prompt's own `Section i` / `turn j:` layout and
    flags every turn that contains the marker, with its local indices."""
    claims = []
    section = 0
    for line in prompt_text.splitlines():
        if m := _SECTION_RE.match(line):
            section = int(m.group(1))
        elif (m := _TURN_RE.match(line)) and _MARKER in m.group(2):
            claims.append(
                ClaimCheck(
                    section_index=section,
                    turn_index=int(m.group(1)),
                    claim=f"revenue hit {_MARKER}",
                    evidence="not in the source",
                    verdict="unsupported",
                    suggested_fix="drop the figure",
                )
            )
    return GroundingChecks(checks=claims)


def _draft(total_words: int, marker: bool = False) -> SectionDraft:
    """A valid story draft of about total_words words (turns kept well under
    600 characters), optionally with the marker planted in turn 1."""
    n_turns = max(3, math.ceil(total_words / 60))
    turns = []
    for i in range(n_turns):
        text = ("word " * (total_words // n_turns)).strip()
        if marker and i == 1:
            text = f"Revenue hit {_MARKER} dollars. " + text
        turns.append(Turn(speaker="host_a" if i % 2 == 0 else "host_b", text=text))
    return SectionDraft(turns=turns)


# make_user_with_episode's 3-minute episode: a 345-word story budget. FakeLLM's
# outline fixture asks for 100 words per section; scale_max_words (D-62's 1.3x
# scale-up cap) is what actually decides each section's ceiling, so the test
# drafts are sized from that -- not the raw story budget -- to stay valid.
_STORY_BUDGET = word_budget(3)[2]
_ONE_STORY = scale_max_words([100], _STORY_BUDGET)[0]
_TWO_STORIES = scale_max_words([100, 100], _STORY_BUDGET)[0]


def _episode(db, n_articles: int = 2, focus: str | None = None, topics=None):
    episode = make_user_with_episode(db)
    episode.focus_request = focus
    articles = []
    for i in range(n_articles):
        article = Article(
            url_hash=f"hash-{i}",
            url=f"https://www.outlet{i}.com/story",
            outlet=f"www.outlet{i}.com",
            title=f"Story {i}",
            content="The company reported strong quarterly results and steady growth.",
            content_source=ContentSource.TEXT,
        )
        db.add(article)
        db.flush()
        topic = (topics or ["general"] * n_articles)[i]
        db.add(
            EpisodeItem(
                episode_id=episode.id, article_id=article.id, position=i, story_id=f"s{i + 1}"
            )
        )
        db.add(ArticleScore(episode_id=episode.id, article_id=article.id, topic=topic, score=0.9))
        articles.append(article)
    db.flush()
    return episode, articles


def _adapters(llm) -> Adapters:
    return Adapters(search=None, llm=llm, classifier=None, tts=None)  # type: ignore[arg-type]


def test_run_writes_intro_stories_outro_with_outline_attached(db) -> None:
    episode, articles = _episode(db, 3)
    llm = _StubLLM()

    usage = script.run(episode, _adapters(llm), db)

    kinds = [s["kind"] for s in episode.script["sections"]]
    assert kinds == ["intro", "story", "story", "story", "outro"]
    assert episode.script["outline"]["cold_open_hook"] == "A fake hook."
    assert [s["source_ids"] for s in episode.script["sections"][1:4]] == [
        [short_id(a.id)] for a in articles
    ]
    assert episode.grounding_flags_initial == [] and episode.grounding_flags_final == []
    assert set(episode.prompt_versions) >= {
        "outline",
        "section_writer",
        "frame",
        "grounding_check",
    }
    # outline + 3 sections + frame on the scripting row; grounding on its own row.
    assert usage.cost_usd == pytest.approx(0.005)
    step = db.scalars(select(PipelineStep).where(PipelineStep.stage == "grounding")).one()
    assert float(step.cost_usd) == pytest.approx(0.004)  # 3 sections + 1 frame check


def test_sections_are_written_sequentially_with_earlier_sections_visible(db) -> None:
    episode, _ = _episode(db, 2)
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    first, second = llm.prompts("SectionDraft")
    assert "this is the first section" in first
    assert "Section 1:\nAlex: This is a fake sentence" in second


def test_section_grounding_includes_previous_story_as_context(db) -> None:
    episode, _ = _episode(db, 3)
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    # The per-section context block (not the prompt's general explanation of
    # the label, which is always present regardless of whether any section
    # actually has one).
    marker = "not a source for this section's own new facts"
    grounds = llm.prompts("GroundingChecks")
    assert marker not in grounds[0]  # section 1 has no previous story
    assert marker in grounds[1]
    assert marker in grounds[2]


def test_a_flagged_section_is_patched_and_regrounded(db) -> None:
    episode, _ = _episode(db, 2)
    # Section 2's draft plants the marker; its patch comes back clean.
    llm = _StubLLM(sections=[None, _draft(_TWO_STORIES, marker=True), _draft(_TWO_STORIES)])

    script.run(episode, _adapters(llm), db)

    # Flag index is the index in the final script: intro 0, story 2 is 2.
    assert [c["section_index"] for c in episode.grounding_flags_initial] == [2]
    assert episode.grounding_flags_final == []
    assert _MARKER not in str(episode.script["sections"])
    patch_prompt = llm.prompts("SectionDraft")[2]
    assert _MARKER in patch_prompt  # the patch saw the draft it was fixing
    assert "- turn 1:" in patch_prompt  # ...and the flag


def test_an_unchanged_patch_leaves_its_flag_as_residual(db) -> None:
    """The patch call returns byte-identical text: nothing changed, so
    nothing is re-checked, and the original flag survives as unfixed."""
    episode, _ = _episode(db, 1)
    llm = _StubLLM(sections=[_draft(_ONE_STORY, marker=True), _draft(_ONE_STORY, marker=True)])

    script.run(episode, _adapters(llm), db)

    assert len(episode.grounding_flags_initial) == 1
    assert episode.grounding_flags_final == episode.grounding_flags_initial


def test_a_patch_is_always_kept_even_if_the_recheck_still_flags_it(db) -> None:
    """D-62: no draft-vs-patch flag-count comparison. A patch that changes
    the flagged turn but is *still* imperfect is kept anyway -- unlike the
    old behaviour (a 1-vs-1 tie kept the original, unpatched draft; see the
    D-59 traces on episode 15710)."""
    episode, _ = _episode(db, 1)
    still_bad = _draft(_ONE_STORY, marker=True)
    still_bad.turns[1] = Turn(
        speaker=still_bad.turns[1].speaker,
        text=f"Actually, revenue hit {_MARKER} dollars too, a different way of saying it.",
    )
    llm = _StubLLM(sections=[_draft(_ONE_STORY, marker=True), still_bad])

    script.run(episode, _adapters(llm), db)

    assert len(episode.grounding_flags_initial) == 1
    assert len(episode.grounding_flags_final) == 1  # re-flagged, but the patch is kept regardless
    assert _MARKER in str(episode.script["sections"])  # the (still imperfect) patch, not reverted
    assert len(llm.prompts("SectionDraft")) == 2  # write + one patch -- no second patch


def test_frame_prompt_never_receives_the_drafted_story_turns(db) -> None:
    episode, _ = _episode(db, 2)
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    frame_prompt = llm.prompts("FrameOutput")[0]
    assert "This is a fake sentence for testing scripts" not in frame_prompt
    assert '"cold_open_hook"' in frame_prompt  # the outline plan, not the written sections


def test_frame_grounding_checks_only_intro_and_outro(db) -> None:
    episode, _ = _episode(db, 2)
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    frame_check = llm.prompts("GroundingChecks")[-1]
    assert frame_check.count("Section ") == 2  # intro, outro -- never the story sections


def test_trace_writes_every_step_when_script_trace_dir_is_set(db, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "script_trace_dir", tmp_path / "trace")
    episode, _ = _episode(db, 2)

    def sneak_in_a_fact(frame_out: FrameOutput) -> FrameOutput:
        frame_out.cold_open_turns[0] = Turn(
            speaker="host_a", text=f"Cold open with revenue at {_MARKER}."
        )
        return frame_out

    # s1 is flagged and patched clean; s2 is never flagged; the frame's cold
    # open is flagged and patched too.
    llm = _StubLLM(
        sections=[_draft(_TWO_STORIES, marker=True), _draft(_TWO_STORIES)],
        frame=sneak_in_a_fact,
    )
    script.run(episode, _adapters(llm), db)

    trace = tmp_path / "trace" / str(episode.id)
    files = {p.relative_to(trace).as_posix() for p in trace.rglob("*") if p.is_file()}
    expected = {
        "00_inputs.md",
        "01_outline.json",
        "01_outline.md",
        "02_s1_draft.md",
        "03_s1_grounding.json",
        "04_s1_patched.md",
        "05_s1_regrounding.json",
        "02_s2_draft.md",
        "03_s2_grounding.json",
        "06_frame.md",
        "07_frame_grounding.json",
        "07_intro_patched.md",
        "07_intro_regrounding.json",
        "08_final.md",
        "calls.json",
    }
    assert expected <= files
    assert not any(f.startswith(("04_s2", "05_s2")) for f in files)  # s2 was never flagged
    assert not any(f.startswith("07_outro") for f in files)  # outro was never flagged

    calls = json.loads((trace / "calls.json").read_text(encoding="utf-8"))
    prompts = sorted(f for f in files if f.startswith("prompts/"))
    assert len(calls) == len(prompts) == len(llm.calls)
    assert [c["step"] for c in calls][:4] == ["outline", "s1_write", "s1_ground", "s1_patch"]

    frame_check = json.loads((trace / "07_frame_grounding.json").read_text(encoding="utf-8"))
    assert any(f["section"] == "intro" for f in frame_check["flags"])
    assert _MARKER not in (trace / "08_final.md").read_text(encoding="utf-8")


def test_trace_writes_nothing_when_script_trace_dir_is_unset(db, tmp_path) -> None:
    assert get_settings().script_trace_dir is None
    episode, _ = _episode(db, 2)
    script.run(episode, _adapters(_StubLLM()), db)

    assert episode.script is not None
    assert list(tmp_path.rglob("*")) == []  # tmp_path is also conftest's data_dir


def test_outline_retry_sees_the_previous_outline_and_errors(db) -> None:
    episode, articles = _episode(db, 2)
    bad = Outline(cold_open_hook="h", sections=[], dropped=[])
    llm = _StubLLM(outlines=[bad])

    script.run(episode, _adapters(llm), db)

    retry = llm.prompts("Outline")[1]
    assert "Your previous outline was" in retry
    assert "no sections" in retry
    assert len(episode.script["sections"]) == 4


def test_an_outline_invalid_twice_fails_with_the_spend_attached(db) -> None:
    episode, _ = _episode(db, 1)
    bad = Outline(cold_open_hook="h", sections=[], dropped=[])
    llm = _StubLLM(outlines=[bad, bad])

    with pytest.raises(ScriptingError) as excinfo:
        script.run(episode, _adapters(llm), db)
    assert "outline invalid after retry" in str(excinfo.value)
    assert excinfo.value.usage.cost_usd == pytest.approx(0.002)


def test_outline_prompt_includes_today_window_start_and_article_text(db) -> None:
    episode, _ = _episode(db, 1)
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    outline_prompt = llm.prompts("Outline")[0]
    assert "Today is" in outline_prompt
    assert "covers news since" in outline_prompt
    assert "article text (first 3000 chars):" in outline_prompt


def test_focus_is_rendered_as_the_listener_request_never_the_word_focus(db) -> None:
    episode, _ = _episode(db, 2, focus="open-weight models", topics=["general", "focus"])
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    outline_prompt = llm.prompts("Outline")[0]
    assert 'Listener\'s request for this episode: "open-weight models"' in outline_prompt
    assert "— focus —" not in outline_prompt
    assert "whose topic is the listener's request" in outline_prompt
    assert "the listener asked about this" in llm.prompts("FrameOutput")[0]


def test_no_focus_section_means_no_you_asked_about(db) -> None:
    # A focus request, but no focus article was selected.
    episode, _ = _episode(db, 2, focus="open-weight models")
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    assert 'Do not say "you asked about..."' in llm.prompts("FrameOutput")[0]
    assert "whose topic is the listener's request" not in llm.prompts("Outline")[0]


def test_episode_items_follow_the_outline_order(db) -> None:
    episode, articles = _episode(db, 3)
    a0, a1, a2 = (short_id(a.id) for a in articles)
    prompt = RenderedPrompt(name="outline", version=1, text=f"[{a2}] [{a0}] [{a1}]")
    fake_outline, _ = FakeLLM().structured(prompt, Outline, "m", "r")
    fake_outline.sections[1].source_ids = [a0, a1]  # merge a0 + a1
    fake_outline.sections.pop(2)
    llm = _StubLLM(outlines=[fake_outline])

    script.run(episode, _adapters(llm), db)

    items = {
        short_id(i.article_id): i
        for i in db.scalars(select(EpisodeItem).where(EpisodeItem.episode_id == episode.id))
    }
    assert [items[x].position for x in (a2, a0, a1)] == [0, 1, 2]
    assert [items[x].story_id for x in (a2, a0, a1)] == ["s1", "s2", "s2"]


def test_outlet_domain_and_thin_sources_are_labelled_for_the_model(db) -> None:
    episode, articles = _episode(db, 1)
    articles[0].content = None
    articles[0].highlights = ["A single highlight."]
    articles[0].content_source = ContentSource.HIGHLIGHTS
    llm = _StubLLM()
    script.run(episode, _adapters(llm), db)

    outline_prompt = llm.prompts("Outline")[0]
    # D-62: the raw domain, not a display name -- the model infers the name itself.
    assert "www.outlet0.com —" in outline_prompt
    assert "highlights only" in outline_prompt
    assert "thin source" in llm.prompts("SectionDraft")[0]
