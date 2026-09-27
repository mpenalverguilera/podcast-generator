import struct

from app.schemas import Turn, Usage

_SAMPLE_RATE = 44100
_CHARS_PER_SECOND = 15


def _silent_wav(duration_s: float) -> bytes:
    n_samples = int(_SAMPLE_RATE * max(duration_s, 0.1))
    data = b"\x00\x00" * n_samples
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        _SAMPLE_RATE,
        _SAMPLE_RATE * 2,
        2,
        16,
        b"data",
        len(data),
    )
    return header + data


class FakeTTS:
    """Deterministic TTS for tests/CLI iteration: returns silence sized to the
    text length (roughly 15 characters/second of speech), zero cost."""

    provider = "fake"

    def synthesize_chunk(
        self, turns: list[Turn], seed: int | None, voices: dict[str, str]
    ) -> tuple[bytes, Usage]:
        total_chars = sum(len(t.text) for t in turns)
        duration_s = total_chars / _CHARS_PER_SECOND
        audio = _silent_wav(duration_s)
        usage = Usage(provider="fake", units_in=total_chars, usage_source="fake")
        return audio, usage
