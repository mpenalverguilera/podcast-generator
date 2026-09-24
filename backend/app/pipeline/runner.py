import logging
import time
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters import get_adapters
from app.config import get_settings
from app.db import session_scope
from app.models import Episode, EpisodeStatus, PipelineStep, StepStatus
from app.pipeline import STAGE_ORDER

logger = logging.getLogger(__name__)


def _stage_index(status: EpisodeStatus) -> int:
    for i, (stage_status, _) in enumerate(STAGE_ORDER):
        if stage_status == status:
            return i
    raise ValueError(f"{status} is not a pipeline stage")


def _start_index(episode: Episode) -> int:
    """episode.status always means 'the next stage to attempt', except the
    terminal ready/failed values. This single rule gives 'skip completed
    stages' and 'resume from failed_stage' for free, with no separate index
    bookkeeping: pending starts at the first stage; failed resumes at
    failed_stage (re-attempted, since it never completed); anything else
    (a prior stop_after, or an unclean crash mid-stage) starts at that same
    status, since it hasn't completed either."""
    if episode.status == EpisodeStatus.READY:
        return len(STAGE_ORDER)
    if episode.status == EpisodeStatus.PENDING:
        return 0
    if episode.status == EpisodeStatus.FAILED:
        if not episode.failed_stage:
            raise ValueError(f"episode {episode.id} is failed but has no failed_stage")
        return _stage_index(EpisodeStatus(episode.failed_stage))
    return _stage_index(episode.status)


def _daily_spend_usd(db: Session, today: date) -> float:
    total = db.scalar(
        select(func.coalesce(func.sum(PipelineStep.cost_usd), 0)).where(
            func.date(PipelineStep.started_at) == today
        )
    )
    return float(total or 0.0)


def run_episode(
    episode_id: int, stop_after: str | None = None, tts_override: str | None = None
) -> Episode:
    settings = get_settings()
    adapters = get_adapters(settings, {"tts": tts_override} if tts_override else None)

    with session_scope() as db:
        episode = db.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"episode {episode_id} not found")

        if episode.status == EpisodeStatus.READY:
            logger.info("episode %s already ready, nothing to do", episode_id)
            return episode

        start = _start_index(episode)
        logger.info(
            "episode %s pipeline start: resuming from stage %s%s",
            episode.id,
            STAGE_ORDER[start][0].value if start < len(STAGE_ORDER) else "(none, already ready)",
            f", tts override={tts_override}" if tts_override else "",
        )
        for idx in range(start, len(STAGE_ORDER)):
            stage_status, stage_module = STAGE_ORDER[idx]
            stage_name = stage_status.value

            today = datetime.now(UTC).date()
            if _daily_spend_usd(db, today) >= settings.daily_spend_cap_usd:
                episode.status = EpisodeStatus.FAILED
                episode.failed_stage = stage_name
                episode.error = "daily spend cap exceeded"
                logger.warning(
                    "episode %s stopped before %s: daily spend cap exceeded", episode.id, stage_name
                )
                return episode

            logger.info("episode %s -> entering stage %s", episode.id, stage_name)
            stage_start = time.monotonic()
            started_at = datetime.now(UTC)
            try:
                usage = stage_module.run(episode, adapters, db)
            except Exception as exc:
                latency_ms = int((time.monotonic() - stage_start) * 1000)
                db.add(
                    PipelineStep(
                        episode_id=episode.id,
                        stage=stage_name,
                        status=StepStatus.FAILED,
                        provider="unknown",
                        latency_ms=latency_ms,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error=str(exc),
                    )
                )
                episode.status = EpisodeStatus.FAILED
                episode.failed_stage = stage_name
                episode.error = str(exc)
                logger.error(
                    "episode %s stage %s failed after %dms: %s",
                    episode.id,
                    stage_name,
                    latency_ms,
                    exc,
                )
                return episode

            latency_ms = usage.latency_ms or int((time.monotonic() - stage_start) * 1000)
            db.add(
                PipelineStep(
                    episode_id=episode.id,
                    stage=stage_name,
                    status=StepStatus.SUCCESS,
                    provider=usage.provider,
                    model=usage.model,
                    units_in=usage.units_in,
                    units_out=usage.units_out,
                    cost_usd=usage.cost_usd,
                    cost_is_estimate=usage.cost_is_estimate,
                    usage_source=usage.usage_source,
                    provider_request_id=usage.request_id,
                    latency_ms=latency_ms,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
            )
            episode.failed_stage = None
            episode.error = None
            logger.info(
                "episode %s stage %s succeeded in %dms cost=$%.4f",
                episode.id,
                stage_name,
                latency_ms,
                usage.cost_usd,
            )

            has_next = idx + 1 < len(STAGE_ORDER)
            next_status = STAGE_ORDER[idx + 1][0] if has_next else EpisodeStatus.READY
            episode.status = next_status
            if next_status == EpisodeStatus.READY:
                episode.ready_at = datetime.now(UTC)
                logger.info("episode %s ready: %r", episode.id, episode.title)
            db.flush()

            if stage_name == stop_after:
                logger.info("episode %s stopped after %s (--stop-after)", episode.id, stage_name)
                return episode

        return episode
