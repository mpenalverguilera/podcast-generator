from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Episode
from app.schemas import Usage


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    query = episode.focus_request or "latest news this week"
    _, usage = adapters.search.search(query, since=episode.window_start)
    return usage
