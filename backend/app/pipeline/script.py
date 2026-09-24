import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.config import get_settings
from app.models import Article, Episode, EpisodeItem, Preferences
from app.prompts import load_prompt
from app.schemas import RenderedPrompt, Script, Usage

logger = logging.getLogger(__name__)

_WORDS_PER_MINUTE = 150
_WORD_BUDGET_TOLERANCE = 0.15
_MAX_TURN_CHARS = 600
_ARTICLE_TEXT_LIMIT = 6000
_AUDIO_TAG_RE = re.compile(r"\[[^\]]*\]")


def short_id(article_id: int) -> str:
    return f"a{article_id}"


def strip_audio_tags(text: str) -> str:
    """Removes eleven_v3 audio tags like [laughs] and collapses the resulting
    double spaces -- used for the UI transcript (ARCHITECTURE §5.6)."""
    return re.sub(r"\s+", " ", _AUDIO_TAG_RE.sub("", text)).strip()


def build_articles_block(
    items: list[EpisodeItem], articles: dict[int, Article]
) -> tuple[str, set[str]]:
    """The numbered article block the script_writer prompt is built around
    (docs/phases/03-pipeline.md step 3): `[aNN] Outlet — Date — Title` followed
    by the article text, truncated here (not in the DB, per ARCHITECTURE
    §5.4) since only the prompt needs the shorter form."""
    blocks = []
    ids: set[str] = set()
    for item in items:
        article = articles[item.article_id]
        sid = short_id(article.id)
        ids.add(sid)
        text = (article.content or "\n".join(article.highlights or []))[:_ARTICLE_TEXT_LIMIT]
        date = article.published_at.date().isoformat() if article.published_at else "undated"
        outlet = article.outlet or "unknown outlet"
        title = article.title or "(untitled)"
        blocks.append(f"[{sid}] {outlet} — {date} — {title}\n{text}")
    return "\n\n".join(blocks), ids


def word_budget(target_minutes: int) -> tuple[int, int]:
    budget = target_minutes * _WORDS_PER_MINUTE
    lo = round(budget * (1 - _WORD_BUDGET_TOLERANCE))
    hi = round(budget * (1 + _WORD_BUDGET_TOLERANCE))
    return lo, hi


def _word_count(script: Script) -> int:
    return sum(len(turn.text.split()) for section in script.sections for turn in section.turns)


def validate_script(script: Script, target_minutes: int, selected_ids: set[str]) -> list[str]:
    """Schema validity is already enforced by structured output; this checks
    the rules that a schema can't (docs/phases/03-pipeline.md step 3 /
    ARCHITECTURE §5.5): word budget, every story cites >=1 selected source,
    every cited id is actually selected, no turn over ~600 characters."""
    errors: list[str] = []
    lo, hi = word_budget(target_minutes)
    words = _word_count(script)
    if not (lo <= words <= hi):
        errors.append(
            f"word count {words} outside the {lo}-{hi} budget for {target_minutes} minutes"
        )

    for section in script.sections:
        if section.kind == "story" and not section.source_ids:
            errors.append(f"story section {section.story_id!r} has no source_ids")
        for sid in section.source_ids:
            if sid not in selected_ids:
                errors.append(f"source id {sid!r} is not among the selected articles")
        for turn in section.turns:
            if len(turn.text) > _MAX_TURN_CHARS:
                errors.append(
                    f"a {section.kind} turn is {len(turn.text)} characters, over the "
                    f"{_MAX_TURN_CHARS}-character limit"
                )
    return errors


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    settings = get_settings()
    items = db.scalars(
        select(EpisodeItem)
        .where(EpisodeItem.episode_id == episode.id)
        .order_by(EpisodeItem.position)
    ).all()
    if not items:
        raise RuntimeError(f"episode {episode.id} has no selected items; ranking produced nothing")

    articles = {
        a.id: a
        for a in db.scalars(select(Article).where(Article.id.in_([i.article_id for i in items])))
    }
    articles_block, selected_ids = build_articles_block(items, articles)

    prefs = db.get(Preferences, episode.user_id)
    host_a = (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex"
    host_b = (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam"
    tone = (prefs.tone if prefs and prefs.tone else None) or "warm, informed, a little playful"
    lo, hi = word_budget(episode.target_minutes)

    prompt = load_prompt(
        "script_writer",
        host_a=host_a,
        host_b=host_b,
        tone=tone,
        target_minutes=str(episode.target_minutes),
        word_budget=str((lo + hi) // 2),
        focus_request=episode.focus_request or "(none)",
        articles=articles_block,
    )

    script, usage = adapters.llm.structured(
        prompt, Script, model=settings.model_script, reasoning=settings.model_script_reasoning
    )
    errors = validate_script(script, episode.target_minutes, selected_ids)
    total_usage = usage

    if errors:
        logger.info("episode %s script validation failed, retrying once: %s", episode.id, errors)
        retry_prompt = RenderedPrompt(
            name=prompt.name,
            version=prompt.version,
            text=prompt.text
            + "\n\nYour previous attempt had these problems -- fix them:\n"
            + "\n".join(f"- {e}" for e in errors),
        )
        script, usage2 = adapters.llm.structured(
            retry_prompt,
            Script,
            model=settings.model_script,
            reasoning=settings.model_script_reasoning,
        )
        errors = validate_script(script, episode.target_minutes, selected_ids)
        if errors:
            raise RuntimeError(f"script validation failed after retry: {'; '.join(errors)}")
        total_usage = Usage(
            provider=usage.provider,
            model=usage.model,
            units_in=usage.units_in + usage2.units_in,
            units_out=usage.units_out + usage2.units_out,
            cost_usd=usage.cost_usd + usage2.cost_usd,
            cost_is_estimate=usage.cost_is_estimate,
            latency_ms=usage.latency_ms + usage2.latency_ms,
            usage_source=usage.usage_source,
        )

    episode.script = script.model_dump()
    episode.title = script.title
    episode.summary = script.summary
    episode.prompt_versions = {**(episode.prompt_versions or {}), prompt.name: prompt.version}

    logger.info(
        "episode %s scripted %d words across %d sections, cost=$%.4f",
        episode.id,
        _word_count(script),
        len(script.sections),
        total_usage.cost_usd,
    )
    return total_usage
