import logging
import shutil
import subprocess
import time
from pathlib import Path

from pydub import AudioSegment
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.config import get_settings
from app.models import Episode
from app.pipeline.voice import chunk_extension
from app.schemas import Usage

logger = logging.getLogger(__name__)

_SILENCE_MS = 600
# Longer than the inter-section gap: a pause this size after the last line
# reads as a deliberate close rather than another section boundary, so the
# episode doesn't cut off the instant the hosts stop talking.
_OUTRO_SILENCE_MS = 1500
# Podcast loudness standard (ARCHITECTURE §5.7 / elevenlabs-dialogue skill).
_LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"
# ElevenLabs' "pcm_44100" is raw, headerless 16-bit signed little-endian audio
# at 44100 Hz with no channel count in the file itself -- pydub can't sniff
# these from the bytes the way it can a real container (wav/mp3), so they must
# be passed explicitly. Confirmed empirically against a real episode's chunks
# (docs/DECISIONS.md): decoding as mono matches the chunks' expected spoken
# duration; stereo would imply half the actual speech length.
_PCM_SAMPLE_WIDTH = 2
_PCM_FRAME_RATE = 44100
_PCM_CHANNELS = 1


def _chunk_paths(episode_id: int, ext: str, data_dir: Path) -> list[Path]:
    chunk_dir = Path(data_dir) / "chunks" / str(episode_id)
    return sorted(chunk_dir.glob(f"*.{ext}"), key=lambda p: int(p.stem))


def _load_chunk(path: Path, ext: str) -> AudioSegment:
    if ext == "pcm":
        return AudioSegment(
            data=path.read_bytes(),
            sample_width=_PCM_SAMPLE_WIDTH,
            frame_rate=_PCM_FRAME_RATE,
            channels=_PCM_CHANNELS,
        )
    return AudioSegment.from_file(path)


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    ext = chunk_extension(settings)
    paths = _chunk_paths(episode.id, ext, settings.data_dir)
    if not paths:
        raise RuntimeError(f"episode {episode.id} has no voice chunks to assemble")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found on PATH; install it locally (docs/phases/README.md prerequisites)"
        )

    start = time.monotonic()
    silence = AudioSegment.silent(duration=_SILENCE_MS)
    combined = AudioSegment.empty()
    for i, path in enumerate(paths):
        if i > 0:
            combined += silence
        combined += _load_chunk(path, ext)
    combined += AudioSegment.silent(duration=_OUTRO_SILENCE_MS)

    audio_dir = Path(settings.data_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    raw_path = audio_dir / f"{episode.id}.raw.wav"
    final_path = audio_dir / f"{episode.id}.mp3"
    combined.export(raw_path, format="wav")

    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(raw_path),
                "-af",
                _LOUDNORM_FILTER,
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                str(final_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed assembling episode {episode.id}: {exc.stderr}") from exc
    finally:
        raw_path.unlink(missing_ok=True)

    latency_ms = int((time.monotonic() - start) * 1000)
    episode.audio_path = str(final_path)
    episode.duration_s = len(combined) / 1000.0

    logger.info(
        "episode %s assembled %d chunks into %s (%.1fs)",
        episode.id,
        len(paths),
        final_path,
        episode.duration_s,
    )
    return Usage(provider="local", cost_usd=0.0, cost_is_estimate=False, latency_ms=latency_ms)
