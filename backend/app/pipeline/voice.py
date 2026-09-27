import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.config import Settings, get_settings
from app.models import Episode
from app.pricing import cost_for
from app.schemas import Script, Turn, Usage
from app.spend import daily_spend_usd

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


class VoiceStageError(RuntimeError):
    """Some chunks failed. Carries the usage of the chunks that did succeed
    (their audio is on disk and already paid for) so the runner records that
    spend on the failed row instead of losing it. D-56."""

    def __init__(self, message: str, usage: Usage) -> None:
        super().__init__(message)
        self.usage = usage


def _aggregate_usage(usages: list[Usage], provider: str, wall_ms: int) -> Usage:
    """latency_ms is the stage's wall-clock time, not the sum of chunk
    latencies: with chunks in parallel the sum overstates the real wait."""
    if not usages:
        return Usage(
            provider=provider,
            cost_usd=0.0,
            cost_is_estimate=provider == "elevenlabs",
            latency_ms=wall_ms,
            usage_source="exact",
        )
    return Usage(
        provider=usages[0].provider,
        model=usages[0].model,
        units_in=sum(u.units_in for u in usages),
        units_out=sum(u.units_out for u in usages),
        cost_usd=sum(u.cost_usd for u in usages),
        cost_is_estimate=usages[0].cost_is_estimate,
        latency_ms=wall_ms,
        usage_source=usages[0].usage_source,
    )


def _write_atomic(path: Path, data: bytes) -> None:
    """A crash mid-write must not leave a truncated chunk that a later retry
    would treat as done and skip."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _resolve_voices(episode: Episode, settings: Settings) -> dict[str, str]:
    """The user's saved voice_id per host if set, else the .env default. D-58:
    resolved once per episode (not per chunk or per adapter call) so a mid-run
    preference change can't split one episode across two voices for the same
    speaker."""
    prefs = episode.user.preferences
    defaults = {"host_a": settings.default_voice_host_a, "host_b": settings.default_voice_host_b}
    voices: dict[str, str] = {}
    for speaker, default in defaults.items():
        saved = (getattr(prefs, speaker, None) or {}) if prefs else {}
        voice_id = saved.get("voice_id") or default
        if not voice_id:
            raise RuntimeError(
                f"no voice_id for {speaker}: set preferences.{speaker}.voice_id or "
                f"DEFAULT_VOICE_{speaker.upper()} before voicing episode {episode.id}"
            )
        voices[speaker] = voice_id
    return voices


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    voices = _resolve_voices(episode, settings)
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

    # Resume-safe: a chunk already on disk (from a prior attempt that failed
    # later) is never re-requested and never re-billed.
    missing = [
        (i, turns) for i, turns in enumerate(chunks) if not (chunk_dir / f"{i}.{ext}").exists()
    ]
    missing_chars = sum(len(t.text) for _, turns in missing for t in turns)

    # The runner only checked we're under the cap before this stage; every
    # missing chunk goes out at once, so check the whole batch fits first.
    estimate_usd, _ = cost_for(adapters.tts.provider, settings.elevenlabs_model, missing_chars)
    spent_usd = daily_spend_usd(db, datetime.now(UTC).date())
    if estimate_usd and spent_usd + estimate_usd > settings.daily_spend_cap_usd:
        raise RuntimeError(
            f"voicing {missing_chars} chars (~${estimate_usd:.2f}) would take today's spend "
            f"${spent_usd:.2f} over DAILY_SPEND_CAP_USD={settings.daily_spend_cap_usd}"
        )

    def synthesize(i: int, turns: list[Turn]) -> Usage:
        # Runs on a worker thread: touches only the adapter and the file
        # system, never the DB session or the Episode object.
        audio_bytes, usage = adapters.tts.synthesize_chunk(turns, seed=seed, voices=voices)
        _write_atomic(chunk_dir / f"{i}.{ext}", audio_bytes)
        return usage

    # Bounds this episode's requests in flight; the ElevenLabs adapter's
    # process-wide semaphore bounds all concurrent episodes together.
    workers = max(1, min(settings.elevenlabs_max_concurrency, len(missing)))
    usages: list[Usage] = []
    failures: list[tuple[int, BaseException]] = []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="voice") as pool:
        futures = {pool.submit(synthesize, i, turns): i for i, turns in missing}
        for future in as_completed(futures):
            if future.exception() is not None:
                # Don't start chunks still queued; in-flight ones finish
                # (they're already paid for) and keep their files. Not
                # pool.shutdown(cancel_futures=True): that never wakes
                # as_completed for the dropped futures, so it hangs.
                for f in futures:
                    f.cancel()
                break
    # Leaving the `with` waited for every chunk that had started.
    wall_ms = int((time.monotonic() - start) * 1000)
    for future, i in futures.items():
        if future.cancelled():
            continue
        exc = future.exception()
        if exc is None:
            usages.append(future.result())
        else:
            failures.append((i, exc))
    usage = _aggregate_usage(usages, adapters.tts.provider, wall_ms)

    if failures:
        first_index, first_exc = failures[0]
        raise VoiceStageError(
            f"{len(failures)} of {len(missing)} chunks failed "
            f"({len(usages)} synthesized and kept); chunk {first_index}: {first_exc}",
            usage,
        ) from first_exc

    db.flush()
    logger.info(
        "episode %s voiced %d chunks (%d skipped, already synthesized), %d chars, "
        "workers=%d, wall=%dms (sum of chunk calls %dms), cost=$%.4f",
        episode.id,
        len(chunks),
        len(chunks) - len(missing),
        total_chars,
        workers,
        wall_ms,
        sum(u.latency_ms or 0 for u in usages),
        usage.cost_usd,
    )
    return usage
