import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from elevenlabs.core.api_error import ApiError

from app.adapters import Adapters
from app.adapters.tts import elevenlabs as elevenlabs_module
from app.adapters.tts.elevenlabs import ElevenLabsDialogueTTS
from app.config import Settings, get_settings
from app.models import PipelineStep, StepStatus
from app.pipeline import voice
from app.pipeline.voice import VoiceStageError, chunk_extension, chunk_script
from app.schemas import Script, Section, Turn, Usage
from tests.conftest import make_user_with_episode


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


# --- parallel voice stage ---------------------------------------------------

_LETTERS = "abcde"


class _TrackingTTS:
    """Records calls and the peak number of simultaneous calls; fails on any
    chunk whose first turn starts with one of `fail_on`."""

    def __init__(self, provider: str = "fake", fail_on: str = "", delay_s: float = 0.05) -> None:
        self.provider = provider
        self.fail_on = fail_on
        self.delay_s = delay_s
        self.calls: list[str] = []
        self.voices_seen: list[dict[str, str]] = []
        self.in_flight = 0
        self.peak = 0
        self._lock = threading.Lock()

    def synthesize_chunk(
        self, turns: list[Turn], seed: int | None, voices: dict[str, str]
    ) -> tuple[bytes, Usage]:
        letter = turns[0].text[0]
        with self._lock:
            self.calls.append(letter)
            self.voices_seen.append(voices)
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            time.sleep(self.delay_s)
            if letter in self.fail_on:
                raise RuntimeError(f"boom on {letter}")
            chars = sum(len(t.text) for t in turns)
            return letter.encode(), Usage(
                provider=self.provider, units_in=chars, cost_usd=chars / 10_000, latency_ms=50
            )
        finally:
            with self._lock:
                self.in_flight -= 1


def _voiced_episode(db):
    """An episode with 5 one-turn sections of 1,500 chars -> 5 chunks."""
    episode = make_user_with_episode(db)
    episode.script = _script(
        *[
            Section(
                kind="story",
                story_id=f"s{i}",
                source_ids=[],
                turns=[Turn(speaker="host_a", text=c * 1500)],
            )
            for i, c in enumerate(_LETTERS)
        ]
    ).model_dump()
    db.commit()
    return episode


def _chunk_dir(episode_id: int) -> Path:
    return Path(get_settings().data_dir) / "chunks" / str(episode_id)


def _chunk_path(episode_id: int, i: int) -> Path:
    return _chunk_dir(episode_id) / f"{i}.{chunk_extension(get_settings())}"


def _adapters(tts) -> Adapters:
    return Adapters(search=None, llm=None, classifier=None, tts=tts)  # type: ignore[arg-type]


def test_voicing_runs_chunks_in_parallel_up_to_the_concurrency_limit(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "elevenlabs_max_concurrency", 2)
    episode = _voiced_episode(db)
    tts = _TrackingTTS()

    usage = voice.run(episode, _adapters(tts), db)

    assert sorted(tts.calls) == list(_LETTERS)
    assert tts.peak == 2
    assert usage.units_in == 5 * 1500
    for i, letter in enumerate(_LETTERS):
        assert _chunk_path(episode.id, i).read_bytes() == letter.encode()
    assert not list(_chunk_dir(episode.id).glob("*.part"))
    # D-58: every chunk, including ones synthesized concurrently, gets the
    # same resolved voice mapping (here, the test defaults from conftest).
    assert tts.voices_seen == [{"host_a": "test-voice-a", "host_b": "test-voice-b"}] * len(_LETTERS)


def test_latency_is_wall_clock_not_the_sum_of_chunks(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "elevenlabs_max_concurrency", 5)
    episode = _voiced_episode(db)
    tts = _TrackingTTS(delay_s=0.2)

    usage = voice.run(episode, _adapters(tts), db)

    # 5 chunks x 0.2 s run together: ~0.2 s of wall time, not 1.0 s.
    assert usage.latency_ms < 700


def test_already_synthesized_chunks_are_skipped(db) -> None:
    episode = _voiced_episode(db)
    _chunk_dir(episode.id).mkdir(parents=True, exist_ok=True)
    _chunk_path(episode.id, 0).write_bytes(b"kept")
    _chunk_path(episode.id, 2).write_bytes(b"kept")
    tts = _TrackingTTS()

    voice.run(episode, _adapters(tts), db)

    assert sorted(tts.calls) == ["b", "d", "e"]
    assert _chunk_path(episode.id, 0).read_bytes() == b"kept"


# --- voice resolution (D-58) -------------------------------------------------


def _set_saved_voice(db, episode, speaker: str, voice_id: str) -> None:
    prefs = episode.user.preferences
    saved = dict(getattr(prefs, speaker))
    saved["voice_id"] = voice_id
    setattr(prefs, speaker, saved)
    db.commit()


def test_users_saved_voice_id_is_used_when_set(db) -> None:
    episode = _voiced_episode(db)
    _set_saved_voice(db, episode, "host_a", "user-voice-a")
    tts = _TrackingTTS()

    voice.run(episode, _adapters(tts), db)

    assert tts.voices_seen[0] == {"host_a": "user-voice-a", "host_b": "test-voice-b"}


def test_default_voice_is_used_when_preference_is_empty(db) -> None:
    episode = _voiced_episode(db)  # host_a/host_b prefs have no voice_id (conftest)
    tts = _TrackingTTS()

    voice.run(episode, _adapters(tts), db)

    assert tts.voices_seen[0] == {"host_a": "test-voice-a", "host_b": "test-voice-b"}


def test_raises_clear_error_when_speaker_has_no_voice_id_at_all(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "default_voice_host_b", "")
    episode = _voiced_episode(db)
    tts = _TrackingTTS()

    with pytest.raises(RuntimeError, match="host_b"):
        voice.run(episode, _adapters(tts), db)

    # No paid call was made for any chunk.
    assert tts.calls == []


def test_failed_chunk_keeps_finished_ones_and_reports_their_usage(db, monkeypatch) -> None:
    # One worker: a, b succeed, c fails. The worker may already have picked up
    # d before the cancel lands, but e is never sent.
    monkeypatch.setattr(get_settings(), "elevenlabs_max_concurrency", 1)
    episode = _voiced_episode(db)
    failing = _TrackingTTS(fail_on="c")

    with pytest.raises(VoiceStageError) as excinfo:
        voice.run(episode, _adapters(failing), db)

    assert failing.calls[:3] == ["a", "b", "c"]
    assert "e" not in failing.calls
    synthesized = [c for c in failing.calls if c != "c"]
    assert excinfo.value.usage.units_in == len(synthesized) * 1500
    on_disk = sorted(_LETTERS[int(p.stem)] for p in _chunk_dir(episode.id).iterdir())
    assert on_disk == synthesized

    retry = _TrackingTTS()
    voice.run(episode, _adapters(retry), db)
    assert sorted(retry.calls) == [c for c in _LETTERS if c not in synthesized]


def test_batch_that_would_exceed_the_daily_cap_sends_nothing(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "daily_spend_cap_usd", 1.0)
    episode = _voiced_episode(db)
    db.add(
        PipelineStep(
            episode_id=episode.id,
            stage="scripting",
            status=StepStatus.SUCCESS,
            provider="openai",
            cost_usd=0.5,
            started_at=datetime.now(UTC),
        )
    )
    db.commit()
    # 7,500 chars at the default $0.11/1k = ~$0.83; $0.50 + $0.83 > $1.00.
    tts = _TrackingTTS(provider="elevenlabs")

    with pytest.raises(RuntimeError, match="DAILY_SPEND_CAP_USD"):
        voice.run(episode, _adapters(tts), db)
    assert tts.calls == []


# --- ElevenLabs adapter retry -------------------------------------------------


def _real_adapter(monkeypatch, outcomes: list) -> tuple[ElevenLabsDialogueTTS, list[int]]:
    """An ElevenLabs adapter whose HTTP call is replaced by `outcomes`, one per
    attempt: an exception to raise, or a character-cost to return."""
    monkeypatch.setattr(elevenlabs_module.time, "sleep", lambda _s: None)
    tts = ElevenLabsDialogueTTS(
        Settings(elevenlabs_api_key="test", default_voice_host_a="va", default_voice_host_b="vb")
    )
    attempts: list[int] = []

    def fake_convert(_inputs, _seed):
        attempts.append(1)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return b"audio", {"character-cost": str(outcome)}

    monkeypatch.setattr(tts, "_convert", fake_convert)
    return tts, attempts


_VOICES = {"host_a": "va", "host_b": "vb"}


def test_adapter_retries_429_then_succeeds(monkeypatch) -> None:
    tts, attempts = _real_adapter(
        monkeypatch, [ApiError(status_code=429, headers={"retry-after": "1"}), 12]
    )
    audio, usage = tts.synthesize_chunk(
        [Turn(speaker="host_a", text="hello there")], seed=1, voices=_VOICES
    )
    assert (audio, usage.units_in, len(attempts)) == (b"audio", 12, 2)


def test_adapter_gives_up_after_max_attempts_on_5xx(monkeypatch) -> None:
    tts, attempts = _real_adapter(monkeypatch, [ApiError(status_code=503)] * 3)
    with pytest.raises(ApiError):
        tts.synthesize_chunk([Turn(speaker="host_a", text="hi")], seed=1, voices=_VOICES)
    assert len(attempts) == 3


def test_adapter_does_not_retry_auth_errors(monkeypatch) -> None:
    tts, attempts = _real_adapter(monkeypatch, [ApiError(status_code=401), 5])
    with pytest.raises(ApiError):
        tts.synthesize_chunk([Turn(speaker="host_a", text="hi")], seed=1, voices=_VOICES)
    assert len(attempts) == 1


def test_adapter_maps_each_turn_to_its_speakers_voice_id(monkeypatch) -> None:
    tts, _attempts = _real_adapter(monkeypatch, [1])
    seen_inputs = {}

    def fake_convert(inputs, _seed):
        seen_inputs["inputs"] = inputs
        return b"audio", {"character-cost": "1"}

    monkeypatch.setattr(tts, "_convert", fake_convert)
    turns = [Turn(speaker="host_a", text="hi"), Turn(speaker="host_b", text="there")]

    tts.synthesize_chunk(turns, seed=1, voices={"host_a": "voice-a", "host_b": "voice-b"})

    assert [i["voice_id"] for i in seen_inputs["inputs"]] == ["voice-a", "voice-b"]


def test_request_cap_is_shared_across_adapter_instances(monkeypatch) -> None:
    """Two episodes voicing at once each build their own adapter; together they
    must still stay under the account's concurrency limit."""
    settings = Settings(
        elevenlabs_api_key="test",
        default_voice_host_a="va",
        default_voice_host_b="vb",
        elevenlabs_max_concurrency=2,
    )
    lock = threading.Lock()
    state = {"in_flight": 0, "peak": 0}

    def fake_convert(_inputs, _seed):
        with lock:
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
        threading.Event().wait(0.05)
        with lock:
            state["in_flight"] -= 1
        return b"audio", {"character-cost": "2"}

    adapters = [ElevenLabsDialogueTTS(settings) for _ in range(2)]
    for tts in adapters:
        monkeypatch.setattr(tts, "_convert", fake_convert)

    turns = [Turn(speaker="host_a", text="hi")]
    threads = [
        threading.Thread(
            target=adapters[i % 2].synthesize_chunk, args=(turns, 1), kwargs={"voices": _VOICES}
        )
        for i in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["peak"] == 2
