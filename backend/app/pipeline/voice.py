import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.config import Settings, get_settings
from app.models import Episode
from app.schemas import Script, Turn, Usage

logger = logging.getLogger(__name__)

_MAX_CHUNK_CHARS = 1800


def chunk_extension(settings: Settings) -> str:
    """FakeTTS always returns a self-describing WAV container regardless of
    ELEVENLABS_OUTPUT_FORMAT (that setting only applies to the real adapter),
    so the chunk file extension has to key off the provider, not the format."""
    if settings.tts_provider == "fake":
        return "wav"
    return settings.elevenlabs_output_format.split("_")[0]


def chunk_script(script: Script, max_chars: int = _MAX_CHUNK_CHARS) -> list[list[Turn]]:
    """Chunker for ElevenLabs Text to Dialogue (elevenlabs-dialogue skill):
    walk sections in order, pack whole sections into a chunk while under
    max_chars; a section that doesn't fit the current (non-empty) chunk starts
    a new one; a section too large to fit any chunk alone is split at turn
    boundaries only -- a turn is never split mid-text."""
    chunks: list[list[Turn]] = []
    current: list[Turn] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append(current)
            current = []
            current_len = 0

    for section in script.sections:
        section_turns = section.turns
        section_len = sum(len(t.text) for t in section_turns)

        if current_len + section_len <= max_chars:
            current.extend(section_turns)
            current_len += section_len
        elif section_len <= max_chars:
            flush()
            current.extend(section_turns)
            current_len = section_len
        else:
            flush()
            for turn in section_turns:
                turn_len = len(turn.text)
                if current and current_len + turn_len > max_chars:
                    flush()
                current.append(turn)
                current_len += turn_len

    flush()
    return chunks


def _aggregate_usage(usages: list[Usage]) -> Usage:
    if not usages:
        return Usage(
            provider="elevenlabs", cost_usd=0.0, cost_is_estimate=True, usage_source="exact"
        )
    return Usage(
        provider=usages[0].provider,
        model=usages[0].model,
        units_in=sum(u.units_in for u in usages),
        units_out=sum(u.units_out for u in usages),
        cost_usd=sum(u.cost_usd for u in usages),
        cost_is_estimate=usages[0].cost_is_estimate,
        latency_ms=sum(u.latency_ms for u in usages),
        usage_source=usages[0].usage_source,
    )


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    script = Script.model_validate(episode.script)
    chunks = chunk_script(script)

    total_chars = sum(len(t.text) for chunk in chunks for t in chunk)
    if total_chars > settings.max_tts_chars_per_episode:
        raise RuntimeError(
            f"episode {episode.id} needs {total_chars} TTS characters, over "
            f"MAX_TTS_CHARS_PER_EPISODE={settings.max_tts_chars_per_episode}"
        )

    seed = episode.tts_seed or episode.id
    episode.tts_seed = seed

    ext = chunk_extension(settings)
    chunk_dir = Path(settings.data_dir) / "chunks" / str(episode.id)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    usages: list[Usage] = []
    skipped = 0
    for i, chunk_turns in enumerate(chunks):
        chunk_path = chunk_dir / f"{i}.{ext}"
        if chunk_path.exists():
            # Resume-safe: a chunk already synthesized (from a prior attempt
            # that failed later) is never re-requested and never re-billed.
            skipped += 1
            continue
        audio_bytes, usage = adapters.tts.synthesize_chunk(chunk_turns, seed=seed)
        chunk_path.write_bytes(audio_bytes)
        usages.append(usage)

    db.flush()
    logger.info(
        "episode %s voiced %d chunks (%d skipped, already synthesized), %d chars, cost=$%.4f",
        episode.id,
        len(chunks),
        skipped,
        total_chars,
        sum(u.cost_usd for u in usages),
    )
    return _aggregate_usage(usages)
