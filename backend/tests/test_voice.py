from app.config import Settings
from app.pipeline.voice import chunk_extension, chunk_script
from app.schemas import Script, Section, Turn


def _section(kind: str, n_turns: int, chars_per_turn: int, story_id: str | None = None) -> Section:
    text = "x" * chars_per_turn
    turns = [Turn(speaker="host_a" if i % 2 == 0 else "host_b", text=text) for i in range(n_turns)]
    return Section(kind=kind, story_id=story_id, source_ids=[], turns=turns)


def _script(*sections: Section) -> Script:
    return Script(title="t", summary="s", sections=list(sections))


def test_whole_small_sections_pack_into_one_chunk() -> None:
    script = _script(
        _section("intro", 2, 100),
        _section("story", 3, 100, "s1"),
        _section("outro", 2, 100),
    )
    chunks = chunk_script(script, max_chars=1800)
    assert len(chunks) == 1
    assert sum(len(t.text) for t in chunks[0]) == 700


def test_never_exceeds_max_chars_across_chunks() -> None:
    script = _script(*[_section("story", 2, 900, f"s{i}") for i in range(5)])
    chunks = chunk_script(script, max_chars=1800)
    for chunk in chunks:
        assert sum(len(t.text) for t in chunk) <= 1800


def test_section_that_does_not_fit_starts_a_new_chunk_at_boundary() -> None:
    # intro (1000) + story (1000) would be 2000 > 1800, so the story must
    # start a fresh chunk rather than splitting either section's turns.
    script = _script(_section("intro", 1, 1000), _section("story", 1, 1000, "s1"))
    chunks = chunk_script(script, max_chars=1800)
    assert len(chunks) == 2
    assert len(chunks[0]) == 1
    assert len(chunks[1]) == 1


def test_oversized_section_splits_at_turn_boundaries_never_mid_turn() -> None:
    # A single section of 4 turns x 700 chars = 2800 > 1800: must split, but
    # only between turns.
    script = _script(_section("story", 4, 700, "s1"))
    chunks = chunk_script(script, max_chars=1800)
    assert len(chunks) > 1
    all_turns = [t for chunk in chunks for t in chunk]
    assert len(all_turns) == 4
    for turn in all_turns:
        assert len(turn.text) == 700  # never split mid-turn
    for chunk in chunks:
        assert sum(len(t.text) for t in chunk) <= 1800


def test_chunk_extension_depends_on_provider_not_just_format() -> None:
    fake_settings = Settings(tts_provider="fake", elevenlabs_output_format="mp3_44100_128")
    assert chunk_extension(fake_settings) == "wav"

    real_settings = Settings(tts_provider="elevenlabs", elevenlabs_output_format="mp3_44100_128")
    assert chunk_extension(real_settings) == "mp3"
