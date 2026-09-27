import re

from app.models import ArticleScore, EpisodeItem
from app.pipeline.script import (
    apply_outline_order,
    changed_story_indices,
    check_polish,
    normalize_targets,
    only_word_count_errors,
    outlet_name,
    remap_flags,
    resolve_topics,
    revert_flagged,
    short_id,
    strip_audio_tags,
    validate_outline,
    validate_section,
    word_budget,
)
from app.prompts import DEFAULT_PROMPTS_DIR
from app.schemas import (
    DroppedSource,
    Outline,
    OutlineSection,
    PolishedScript,
    Script,
    Section,
    Turn,
    UnsupportedClaim,
)

_NAMES = ["Alex", "Sam"]


def _turns(n: int, words_each: int = 10) -> list[Turn]:
    speakers = ["host_a", "host_b"]
    return [Turn(speaker=speakers[i % 2], text="word " * words_each) for i in range(n)]


def _plan(story_id: str, source_ids: list[str], target_words: int = 100) -> OutlineSection:
    return OutlineSection(
        story_id=story_id,
        source_ids=source_ids,
        topic_label="t",
        headline="h",
        angle="a",
        why_listener_cares="w",
        depth="headlines",
        target_words=target_words,
        key_facts=[],
        must_not_cover=[],
        bridge_in=None,
    )


def _story(story_id: str, source_ids: list[str], texts: list[str]) -> Section:
    speakers = ["host_a", "host_b"]
    return Section(
        kind="story",
        story_id=story_id,
        source_ids=source_ids,
        turns=[Turn(speaker=speakers[i % 2], text=t) for i, t in enumerate(texts)],
    )


# --- budget ---


def test_word_budget_uses_135_wpm_and_a_12_percent_frame_with_a_floor() -> None:
    assert word_budget(6) == (810, 97, 713)
    # 12% of 405 is 49, below the 60-word floor for an intro + outro.
    assert word_budget(3) == (405, 60, 345)


def test_normalize_targets_keeps_proportions_and_sums_to_the_budget() -> None:
    targets = normalize_targets([100, 300, 100], 1000)
    assert targets == [200, 600, 200]
    assert abs(sum(normalize_targets([120, 250, 90, 80], 713)) - 713) <= 2


def test_normalize_targets_survives_zero_or_negative_targets() -> None:
    assert normalize_targets([0, 0], 300) == [150, 150]


# --- outlet names ---


def test_outlet_name_turns_domains_into_spoken_names() -> None:
    assert outlet_name("www.reuters.com") == "Reuters"
    assert outlet_name("www.nytimes.com") == "The New York Times"
    assert outlet_name("news.bbc.co.uk") == "BBC"
    assert outlet_name("finance.yahoo.com") == "Yahoo"
    assert outlet_name("https://www.the-decoder.com/some/path") == "The Decoder"
    assert outlet_name("Reuters") == "Reuters"  # already a name
    assert outlet_name(None) == "an unnamed outlet"


# --- outline validation ---


def test_validate_outline_accepts_full_coverage_with_merge_and_drop() -> None:
    outline = Outline(
        cold_open_hook="hook",
        sections=[_plan("s1", ["a1", "a2"]), _plan("s2", ["a3"])],
        dropped=[DroppedSource(source_id="a4", reason="no real news")],
    )
    assert validate_outline(outline, {"a1", "a2", "a3", "a4"}) == []


def test_validate_outline_flags_unknown_duplicate_and_missing_ids() -> None:
    outline = Outline(
        cold_open_hook="hook",
        sections=[_plan("s1", ["a1", "a9"]), _plan("s1", ["a1"])],
    )
    errors = validate_outline(outline, {"a1", "a2"})
    assert any("not unique" in e for e in errors)
    assert any("'a9'" in e and "not among" in e for e in errors)
    assert any("'a1'" in e and "2 times" in e for e in errors)
    assert any("'a2'" in e and "no section" in e for e in errors)


def test_validate_outline_flags_an_id_both_in_a_section_and_dropped() -> None:
    outline = Outline(
        cold_open_hook="hook",
        sections=[_plan("s1", ["a1"])],
        dropped=[DroppedSource(source_id="a1", reason="x")],
    )
    assert any("2 times" in e for e in validate_outline(outline, {"a1"}))


def test_validate_outline_needs_a_section() -> None:
    outline = Outline(
        cold_open_hook="hook", sections=[], dropped=[DroppedSource(source_id="a1", reason="x")]
    )
    assert any("no sections" in e for e in validate_outline(outline, {"a1"}))


# --- section validation ---


def test_validate_section_accepts_a_good_story() -> None:
    assert validate_section(_turns(4, 25), _NAMES, 100) == []


def test_validate_section_flags_structure_problems() -> None:
    one_speaker = [Turn(speaker="host_a", text="word " * 30) for _ in range(3)]
    assert any("both hosts" in e for e in validate_section(one_speaker, _NAMES, 90))
    assert any("at least 3" in e for e in validate_section(_turns(2, 50), _NAMES, 100))

    long_turn = [*_turns(2, 10), Turn(speaker="host_a", text="x" * 601)]
    assert any("601 characters" in e for e in validate_section(long_turn, _NAMES, None))

    prefixed = [*_turns(2, 10), Turn(speaker="host_b", text="Sam: I think so.")]
    assert any("speaker name" in e for e in validate_section(prefixed, _NAMES, None))


def test_validate_section_word_count_error_is_distinguishable() -> None:
    errors = validate_section(_turns(3, 10), _NAMES, 100)  # 30 words vs 75-125
    assert only_word_count_errors(errors)
    assert not only_word_count_errors(validate_section(_turns(2, 10), _NAMES, 100))


def test_validate_section_ignores_audio_tags_in_word_count() -> None:
    turns = [Turn(speaker=t.speaker, text="[laughs] " + t.text) for t in _turns(4, 25)]
    assert validate_section(turns, _NAMES, 100) == []


def test_validate_section_for_intro_skips_story_rules() -> None:
    intro = [Turn(speaker="host_a", text="Short open.")]
    assert validate_section(intro, _NAMES, None, is_story=False) == []


# --- polish checks ---


def _polished(sections: list[Section]) -> PolishedScript:
    return PolishedScript(title="t", summary="s", sections=sections)


def _frame(kind: str) -> Section:
    return Section(kind=kind, turns=[Turn(speaker="host_a", text="Hello there.")])


def test_check_polish_accepts_same_stories_between_intro_and_outro() -> None:
    drafts = [_story("s1", ["a1"], ["x", "y", "z"]), _story("s2", ["a2"], ["x", "y", "z"])]
    polished = _polished([_frame("intro"), *drafts, _frame("outro")])
    assert check_polish(polished, drafts) == ([], True)


def test_check_polish_flags_missing_frame_and_reordered_stories() -> None:
    drafts = [_story("s1", ["a1"], ["x", "y", "z"]), _story("s2", ["a2"], ["x", "y", "z"])]
    frame_errors, stories_ok = check_polish(_polished([drafts[1], drafts[0]]), drafts)
    assert any("intro" in e for e in frame_errors)
    assert any("outro" in e for e in frame_errors)
    assert stories_ok is False

    _, stories_ok = check_polish(
        _polished([_frame("intro"), drafts[1], drafts[0], _frame("outro")]), drafts
    )
    assert stories_ok is False


def test_changed_story_indices_ignores_added_audio_tags() -> None:
    drafts = [
        _story("s1", ["a1"], ["One.", "Two.", "Three."]),
        _story("s2", ["a2"], ["Four.", "Five.", "Six."]),
    ]
    polished = [
        _story("s1", ["a1"], ["[laughs] One.", "Two.", "Three."]),  # tags only
        _story("s2", ["a2"], ["Four, and a new bridge.", "Five.", "Six."]),  # words changed
    ]
    assert changed_story_indices(drafts, polished) == [1]


def test_revert_flagged_puts_back_only_the_flagged_drafts() -> None:
    drafts = [_story("s1", ["a1"], ["d1"]), _story("s2", ["a2"], ["d2"])]
    polished = [_story("s1", ["a1"], ["p1"]), _story("s2", ["a2"], ["p2"])]
    result = revert_flagged(polished, drafts, {1})
    assert [s.turns[0].text for s in result] == ["p1", "d2"]


def test_remap_flags_maps_local_indices_to_final_script_indices() -> None:
    def claim(i: int) -> UnsupportedClaim:
        return UnsupportedClaim(
            section_index=i, turn_index=0, claim="c", reason="r", suggested_fix="f"
        )

    # A polish check of [intro, story 2, outro] in a 3-story episode.
    mapped = remap_flags([claim(0), claim(1), claim(2), claim(7)], [0, 2, 4])
    assert [c.section_index for c in mapped] == [0, 2, 4, 0]
    # A one-section check of story 3: whatever the model says, it's section 3.
    assert remap_flags([claim(0)], [3])[0].section_index == 3


def test_apply_outline_order_follows_the_audio_and_merges_story_ids() -> None:
    items = {
        sid: EpisodeItem(episode_id=1, article_id=int(sid[1:]), position=i, story_id=f"s{i + 1}")
        for i, sid in enumerate(["a1", "a2", "a3", "a4"])
    }
    outline = Outline(
        cold_open_hook="h",
        sections=[_plan("x", ["a3"]), _plan("y", ["a1", "a4"])],
        dropped=[DroppedSource(source_id="a2", reason="no news")],
    )
    apply_outline_order(outline, items)

    assert [s.story_id for s in outline.sections] == ["s1", "s2"]
    assert (items["a3"].position, items["a3"].story_id) == (0, "s1")
    assert (items["a1"].position, items["a1"].story_id) == (1, "s2")
    assert (items["a4"].position, items["a4"].story_id) == (2, "s2")  # merged source
    assert (items["a2"].position, items["a2"].story_id) == (3, "s3")  # dropped goes last


def test_resolve_topics_takes_the_best_score_but_the_best_focus_row_is_the_focus_story() -> None:
    scores = [
        # Tied with its focus row -- still the focus story (rank.py's focus slot).
        ArticleScore(article_id=1, topic="open-weight models", score=0.64),
        ArticleScore(article_id=1, topic="focus", score=0.64),
        # Scored higher elsewhere than under focus, and not the best focus row.
        ArticleScore(article_id=2, topic="AI agents", score=0.9),
        ArticleScore(article_id=2, topic="focus", score=0.5),
        ArticleScore(article_id=3, topic="Space", score=0.7),
    ]
    assert resolve_topics(scores) == {1: "focus", 2: "AI agents", 3: "Space"}
    assert resolve_topics(scores[2:]) == {2: "focus", 3: "Space"}


# --- schema / prompts ---


def test_a_v1_script_without_outline_still_validates() -> None:
    v1 = {
        "title": "Old episode",
        "summary": "From before scripting v2.",
        "sections": [
            {"kind": "intro", "story_id": None, "source_ids": [], "turns": []},
            {
                "kind": "story",
                "story_id": "s1",
                "source_ids": ["a1"],
                "turns": [{"speaker": "host_a", "text": "Hi."}],
            },
        ],
    }
    script = Script.model_validate(v1)
    assert script.outline is None
    assert script.trace == []


def test_grounding_policy_text_is_identical_in_writer_patch_and_grounding_prompts() -> None:
    def policy(name: str) -> str:
        text = (DEFAULT_PROMPTS_DIR / name).read_text(encoding="utf-8")
        match = re.search(r"^Grounding policy:\n(?:.+\n)+", text, re.MULTILINE)
        assert match, f"{name} has no grounding policy block"
        return match.group(0)

    blocks = {
        policy(n) for n in ("section_writer.v1.md", "section_patch.v1.md", "grounding_check.v2.md")
    }
    assert len(blocks) == 1


def test_strip_audio_tags_removes_brackets_and_collapses_spaces() -> None:
    assert strip_audio_tags("So [laughs] that happened.") == "So that happened."
    assert strip_audio_tags("[curious] Really?") == "Really?"
    assert strip_audio_tags("No tags here.") == "No tags here."


def test_short_id_format() -> None:
    assert short_id(42) == "a42"
