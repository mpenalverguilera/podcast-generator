from pathlib import Path

import pytest

from app.adapters.tts.fake import _silent_wav
from app.config import get_settings
from app.pipeline import assemble
from app.pipeline.assemble import _load_chunk
from tests.conftest import make_user_with_episode


def test_load_chunk_decodes_headerless_pcm_as_mono_16bit_44100(tmp_path) -> None:
    """ElevenLabs' pcm_44100 output is raw, headerless s16le mono audio -- caught
    live against a real episode (docs/DECISIONS.md): decoding it through
    pydub's generic from_file (which needs a real container/header) raised
    'sample_width', and decoding as stereo would silently halve the duration."""
    one_second_of_silence = b"\x00\x00" * 44100  # 2 bytes/sample, mono, 44100 Hz
    path = tmp_path / "0.pcm"
    path.write_bytes(one_second_of_silence)

    segment = _load_chunk(path, "pcm")

    assert len(segment) == 1000  # pydub reports length in milliseconds
    assert segment.channels == 1
    assert segment.frame_rate == 44100


@pytest.mark.real_ffmpeg
def test_run_applies_the_real_loudnorm_filter(db) -> None:
    """The rest of the suite runs assemble.run with loudnorm swapped for a
    no-op (tests/conftest.py's _fast_test_isolation, for speed); this test
    opts out via the `real_ffmpeg` marker so the production ffmpeg command
    (loudnorm + libmp3lame) is exercised end to end at least once.

    5s of digital silence, not something shorter: libmp3lame's psymodel
    asserts on a too-short loudnorm'd silent clip (observed empirically --
    it fails below ~3s, "Assertion failed: el >= 0 ... psymodel.c"), so this
    keeps a margin above that cliff while staying fast (~0.1s to encode)."""
    episode = make_user_with_episode(db)
    chunk_dir = Path(get_settings().data_dir) / "chunks" / str(episode.id)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (chunk_dir / "0.wav").write_bytes(_silent_wav(5.0))

    usage = assemble.run(episode, adapters=None, db=db)  # type: ignore[arg-type]

    assert Path(episode.audio_path).exists()
    assert episode.duration_s is not None and episode.duration_s > 0
    assert usage.provider == "local"
    assert usage.cost_usd == 0.0
