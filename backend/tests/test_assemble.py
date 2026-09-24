from app.pipeline.assemble import _load_chunk


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
