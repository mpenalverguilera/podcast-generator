import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Article, ContentSource, Episode, EpisodeItem
from app.schemas import Usage

logger = logging.getLogger(__name__)


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    items = db.scalars(
        select(EpisodeItem)
        .where(EpisodeItem.episode_id == episode.id)
        .order_by(EpisodeItem.position)
    ).all()
    if not items:
        raise RuntimeError(f"episode {episode.id} has no selected items; ranking produced nothing")

    article_ids = [item.article_id for item in items]
    articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(article_ids)))}

    # `articles` is a shared cache across users/episodes (ARCHITECTURE §5.2):
    # an article already extracted for a previous episode never needs a new
    # Exa /contents call. Only the genuinely missing ones go out, batched into
    # a single request.
    missing = [a for a in articles.values() if not a.content]
    cached_count = len(articles) - len(missing)

    if not missing:
        usage = Usage(provider="exa", cost_usd=0.0, cost_is_estimate=False, usage_source="exact")
    else:
        results, usage = adapters.search.get_contents([a.url for a in missing])
        now = datetime.now(UTC)
        for article in missing:
            result = results.get(article.url)
            if result is not None and result.status == "success" and result.text:
                article.content = result.text
                article.content_source = ContentSource.TEXT
                article.content_fetched_at = now
            # else: leave the article on its highlights fallback (the default).
        db.flush()

    logger.info(
        "episode %s extract: %d selected, %d already cached, %d fetched, cost=$%.4f",
        episode.id,
        len(articles),
        cached_count,
        len(missing),
        usage.cost_usd,
    )
    return usage
