import logging

from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.config import get_settings
from app.models import Episode
from app.pipeline.context import load_profile, recent_headlines
from app.prompts import load_prompt
from app.schemas import InterestProfile, QueryPlan, Usage

logger = logging.getLogger(__name__)


def _format_topics(profile: InterestProfile) -> str:
    if not profile.topics:
        return "(no topics yet)"
    lines = []
    for t in profile.topics:
        include = ", ".join(t.include) or "none"
        exclude = ", ".join(t.exclude) or "none"
        lines.append(
            f"- {t.name}: {t.description} "
            f"(depth: {t.depth}; include: {include}; exclude: {exclude})"
        )
    return "\n".join(lines)


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    profile = load_profile(db, episode.user_id)
    headlines = recent_headlines(db, episode)

    prompt = load_prompt(
        "query_planner",
        topics=_format_topics(profile),
        avoid=", ".join(profile.avoid) or "none",
        focus_request=episode.focus_request or "(none)",
        window_description=f"since {episode.window_start.isoformat()}",
        recent_headlines="\n".join(f"- {h}" for h in headlines) or "(no recent episodes)",
    )

    plan, usage = adapters.llm.structured(
        prompt, QueryPlan, model=settings.model_planner, reasoning="none"
    )

    episode.planned_queries = [q.model_dump() for q in plan.queries]
    episode.prompt_versions = {**(episode.prompt_versions or {}), prompt.name: prompt.version}
    logger.info(
        "episode %s planned %d queries (%d focus)",
        episode.id,
        len(plan.queries),
        sum(1 for q in plan.queries if q.is_focus),
    )
    return usage
