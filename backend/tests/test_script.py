import re

from app.models import ArticleScore, EpisodeItem
from app.pipeline.script import (
    apply_outline_order,
    banned_phrase_hits,
    changed_turn_indices,
    floor_warning,
    only_word_count_errors,
    outlet_name,
    remap_flags,
    remap_turn_subset,
    resolve_topics,
    scale_max_words,
    short_id,
    strip_audio_tags,
    validate_frame,
    validate_outline,
    validate_section,
    word_budget,
)
from app.prompts import DEFAULT_PROMPTS_DIR
from app.schemas import (
    DroppedSource,
    FrameOutput,
    Outline,
    OutlineSection,
    Turn,
    UnsupportedClaim,
)

_NAMES = ["Alex", "Sam"]


def _turns(n: int, words_each: int = 10) -> list[Turn]:
    speakers = ["host_a", "host_b"]
    return [Turn(speaker=speakers[i % 2], text="word " * words_each) for i in range(n)]


def _plan(story_id: str, source_ids: list[str], max_words: int = 100) -> OutlineSection:
    return OutlineSection(
        story_id=story_id,
        source_ids=source_ids,
        topic_label="t",
        headline="h",
        angle="a",
        stakes="w",
        depth="headlines",
        max_words=max_words,
        key_facts=[],
        must_not_cover=[],
        bridge_in=None,
    )


# --- budget ---


def test_word_budget_uses_135_wpm_and_a_12_percent_frame_clamped_to_120_200() -> None:
    assert word_budget(10) == (1350, 162, 1188)
    # 12% of 810 is 97, below the 120-word floor for an intro + outro (D-65).
    assert word_budget(6) == (810, 120, 690)
    # 12% of 2700 is 324, over the 200-word ceiling.
    assert word_budget(20) == (2700, 200, 2500)


def test_scale_max_words_caps_scaling_up_at_1_3x() -> None:
    # sum=150, budget=1000 -> factor would be 6.67x uncapped; capped at 1.3x.
    assert scale_max_words([100, 50], 1000) == [130, 65]


def test_scale_max_words_scales_down_without_limit() -> None:
    # sum=1000, budget=100 -> factor 0.1x, uncapped.
    assert scale_max_words([600, 400], 100) == [60, 40]


def test_scale_max_words_survives_zero_or_negative_inputs() -> None:
    # weights floor at 1, so the 1.3x scale-up cap applies here too.
    assert scale_max_words([0, 0], 300) == [1, 1]


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


def test_validate_section_only_over_max_by_more_than_10_percent_is_an_error() -> None:
    # max_words=100: up to 110 is fine, 111+ is an error; under 50 is never an error here.
    assert validate_section(_turns(4, 27), _NAMES, 100) == []  # 108 words, +8%: fine
    errors = validate_section(_turns(4, 28), _NAMES, 100)  # 112 words, +12%: over
    assert only_word_count_errors(errors)
    assert validate_section(_turns(3, 2), _NAMES, 100) == []  # 6 words, well under half: no error


def test_floor_warning_only_fires_under_half_the_ceiling() -> None:
    assert floor_warning(60, 100) is None
    assert floor_warning(49, 100) is not None
    assert floor_warning(10, None) is None


def test_validate_section_ignores_audio_tags_in_word_count() -> None:
    turns = [Turn(speaker=t.speaker, text="[laughs] " + t.text) for t in _turns(4, 25)]
    assert validate_section(turns, _NAMES, 100) == []


def test_validate_section_for_intro_skips_story_rules() -> None:
    intro = [Turn(speaker="host_a", text="Short open.")]
    assert validate_section(intro, _NAMES, None, is_story=False) == []


def test_banned_phrase_hits_flags_narrated_personalization() -> None:
    assert banned_phrase_hits("If you follow the AI space, this matters.") == ["if you follow"]
    assert banned_phrase_hits("A totally normal sentence.") == []
    # Multiple phrases in one turn are all reported.
    hits = banned_phrase_hits(
        "For anyone following this, it'll be interesting to see what happens."
    )
    assert set(hits) == {"for anyone following", "it'll be interesting to see"}


def test_banned_phrase_hits_can_exclude_one_phrase() -> None:
    assert banned_phrase_hits("You asked about this.", exclude=frozenset({"you asked about"})) == []


def test_validate_section_rejects_banned_phrases_in_a_story() -> None:
    turns = [*_turns(2, 10), Turn(speaker="host_b", text="As you asked, here's the update.")]
    assert any("banned phrase" in e for e in validate_section(turns, _NAMES, None))


def test_validate_section_allows_you_asked_about_only_for_non_story_sections() -> None:
    story_turns = [*_turns(2, 10), Turn(speaker="host_b", text="You asked about this.")]
    assert any("banned phrase" in e for e in validate_section(story_turns, _NAMES, None))
    frame_turns = [Turn(speaker="host_a", text="You asked about this.")]
    assert validate_section(frame_turns, _NAMES, None, is_story=False) == []


# --- frame validation ---


def _frame(cold_open: int = 1, preview: int = 1, outro: int = 1, asked: int = 0) -> FrameOutput:
    asked_text = " ".join(["You asked about this."] * asked)
    return FrameOutput(
        title="t",
        summary="s",
        cold_open_turns=[
            Turn(
                speaker="host_a",
                text=(f"Cold open {i}. {asked_text}" if i == 0 else f"Cold open {i}."),
            )
            for i in range(cold_open)
        ],
        preview_turns=[Turn(speaker="host_b", text=f"Preview {i}.") for i in range(preview)],
        outro_turns=[Turn(speaker="host_b", text=f"Outro {i}.") for i in range(outro)],
    )


def test_validate_frame_accepts_a_good_frame() -> None:
    assert validate_frame(_frame(), _NAMES, has_focus_section=False) == []


def test_validate_frame_flags_turn_count_shape() -> None:
    assert any("cold_open_turns" in e for e in validate_frame(_frame(cold_open=3), _NAMES, False))
    assert any("preview_turns" in e for e in validate_frame(_frame(preview=0), _NAMES, False))
    assert any("outro_turns" in e for e in validate_frame(_frame(outro=3), _NAMES, False))


def test_validate_frame_you_asked_about_needs_a_focus_section_and_at_most_once() -> None:
    assert any(
        "you asked about" in e
        for e in validate_frame(_frame(asked=1), _NAMES, has_focus_section=False)
    )
    assert validate_frame(_frame(asked=1), _NAMES, has_focus_section=True) == []
    assert any(
        "you asked about" in e
        for e in validate_frame(_frame(asked=2), _NAMES, has_focus_section=True)
    )


# --- patch / re-check machinery ---


def test_changed_turn_indices_finds_only_the_turns_that_actually_changed() -> None:
    before = [Turn(speaker="host_a", text=f"turn {i}") for i in range(3)]
    after = [before[0], Turn(speaker="host_a", text="turn 1 fixed"), before[2]]
    assert changed_turn_indices(before, after) == [1]


def test_changed_turn_indices_ignores_audio_tag_only_changes() -> None:
    before = [Turn(speaker="host_a", text="turn 0")]
    after = [Turn(speaker="host_a", text="[laughs] turn 0")]
    assert changed_turn_indices(before, after) == []


def test_changed_turn_indices_treats_a_turn_count_change_as_all_changed() -> None:
    before = [Turn(speaker="host_a", text="a"), Turn(speaker="host_b", text="b")]
    after = [Turn(speaker="host_a", text="a")]
    assert changed_turn_indices(before, after) == [0]


def test_remap_turn_subset_maps_local_indices_back_to_the_real_turns() -> None:
    def claim(ti: int) -> UnsupportedClaim:
        return UnsupportedClaim(
            section_index=0, turn_index=ti, claim="c", reason="r", suggested_fix="f"
        )

    # A re-check of turns [1, 3] of some section: local 0 -> real 1, local 1 -> real 3.
    mapped = remap_turn_subset([claim(0), claim(1), claim(9)], final_index=2, turn_ids=[1, 3])
    assert [c.section_index for c in mapped] == [2, 2, 2]
    assert [c.turn_index for c in mapped] == [1, 3, 1]  # out-of-range pinned to the first


def test_remap_flags_maps_local_indices_to_final_script_indices() -> None:
    def claim(i: int) -> UnsupportedClaim:
        return UnsupportedClaim(
            section_index=i, turn_index=0, claim="c", reason="r", suggested_fix="f"
        )

    # A frame check of [intro, outro] in a 3-story episode.
    mapped = remap_flags([claim(0), claim(1), claim(7)], [0, 4])
    assert [c.section_index for c in mapped] == [0, 4, 0]
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
    from app.schemas import Script

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
        policy(n) for n in ("section_writer.v3.md", "section_patch.v3.md", "grounding_check.v4.md")
    }
    assert len(blocks) == 1


def test_strip_audio_tags_removes_brackets_and_collapses_spaces() -> None:
    assert strip_audio_tags("So [laughs] that happened.") == "So that happened."
    assert strip_audio_tags("[curious] Really?") == "Really?"
    assert strip_audio_tags("No tags here.") == "No tags here."


def test_short_id_format() -> None:
    assert short_id(42) == "a42"
