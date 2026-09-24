from datetime import UTC, datetime

from app.models import Article, ContentSource, EpisodeItem
from app.pipeline.script import (
    build_articles_block,
    short_id,
    strip_audio_tags,
    validate_script,
    word_budget,
)
from app.schemas import Script, Section, Turn


def _turn(speaker: str, text: str) -> Turn:
    return Turn(speaker=speaker, text=text)


def _valid_script(source_id: str, words_per_section: int = 50) -> Script:
    # "word " * N is exactly N words per section.split() -- 3 sections x 50 =
    # 150 words, the middle of target_minutes=1's [128, 173] budget window.
    text = "word " * words_per_section
    return Script(
        title="t",
        summary="s",
        sections=[
            Section(kind="intro", source_ids=[], turns=[_turn("host_a", text)]),
            Section(
                kind="story", story_id="s1", source_ids=[source_id], turns=[_turn("host_b", text)]
            ),
            Section(kind="outro", source_ids=[], turns=[_turn("host_a", text)]),
        ],
    )


def test_word_budget_is_15_percent_around_150_words_per_minute() -> None:
    lo, hi = word_budget(6)
    assert lo == round(900 * 0.85)
    assert hi == round(900 * 1.15)


def test_validate_script_accepts_a_conforming_script() -> None:
    script = _valid_script("a1")
    errors = validate_script(script, target_minutes=1, selected_ids={"a1"})
    assert errors == []


def test_validate_script_flags_word_count_outside_budget() -> None:
    script = _valid_script("a1")
    errors = validate_script(script, target_minutes=12, selected_ids={"a1"})
    assert any("word count" in e for e in errors)


def test_validate_script_flags_story_with_no_source_ids() -> None:
    script = Script(
        title="t",
        summary="s",
        sections=[
            Section(kind="story", story_id="s1", source_ids=[], turns=[_turn("host_a", "Hi. " * 8)])
        ],
    )
    errors = validate_script(script, target_minutes=1, selected_ids={"a1"})
    assert any("no source_ids" in e for e in errors)


def test_validate_script_flags_source_id_not_selected() -> None:
    script = _valid_script("a999")
    errors = validate_script(script, target_minutes=1, selected_ids={"a1"})
    assert any("a999" in e and "not among the selected" in e for e in errors)


def test_validate_script_flags_turn_over_600_chars() -> None:
    script = Script(
        title="t",
        summary="s",
        sections=[Section(kind="intro", source_ids=[], turns=[_turn("host_a", "x" * 601)])],
    )
    errors = validate_script(script, target_minutes=1, selected_ids=set())
    assert any("601 characters" in e for e in errors)


def test_strip_audio_tags_removes_brackets_and_collapses_spaces() -> None:
    assert strip_audio_tags("So [laughs] that happened.") == "So that happened."
    assert strip_audio_tags("[curious] Really?") == "Really?"
    assert strip_audio_tags("No tags here.") == "No tags here."


def test_short_id_format() -> None:
    assert short_id(42) == "a42"


def test_build_articles_block_truncates_and_orders_by_position() -> None:
    a1 = Article(
        id=1,
        url_hash="h1",
        url="https://example.com/1",
        outlet="Outlet A",
        title="First",
        published_at=datetime(2026, 9, 20, tzinfo=UTC),
        content="x" * 7000,
        content_source=ContentSource.TEXT,
    )
    a2 = Article(
        id=2,
        url_hash="h2",
        url="https://example.com/2",
        outlet="Outlet B",
        title="Second",
        highlights=["short highlight"],
        content_source=ContentSource.HIGHLIGHTS,
    )
    items = [
        EpisodeItem(episode_id=1, article_id=1, position=0, story_id="s1"),
        EpisodeItem(episode_id=1, article_id=2, position=1, story_id="s2"),
    ]
    block, ids = build_articles_block(items, {1: a1, 2: a2})

    assert ids == {"a1", "a2"}
    assert block.index("[a1]") < block.index("[a2]")
    assert "First" in block and "Second" in block
    # Content is truncated for the prompt, not mutated on the article itself.
    assert len(a1.content) == 7000
    a1_block = block.split("[a2]")[0]
    assert a1_block.count("x") <= 6000 + 20  # truncated block, plus header text
